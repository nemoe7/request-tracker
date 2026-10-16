from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, grant_permission, sessions, users
from pwedepa.core import (
  Issue,
  IssueStatus,
  Priority,
  Request,
  RequestStatus,
  Visibility,
)
from pwedepa.data import db as data_db
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.web import SESSION_COOKIE, create_app

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def app(tmp_path):
  return create_app(
    {
      "DATABASE": str(tmp_path / "test.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": True,
    }
  )


@pytest.fixture
def db(app):
  connection = data_db.connect(app.config["DATABASE"])
  yield connection
  connection.close()


def _client(app, db, name, display, roles=(), grants=()):
  person = users.create_user(db, name, display, at=AT)
  for role in roles:
    assign_role(db, person.id, role, at=AT)
  for grant in grants:
    grant_permission(db, person.id, grant, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  return client, person


@pytest.fixture
def cast(app, db):
  admin, admin_user = _client(app, db, "admin", "Ada Admin", roles=(Role.ADMIN,))
  Mara, Mara_user = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  Sam, Sam_user = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  return {
    "admin": (admin, admin_user),
    "Mara": (Mara, Mara_user),
    "Sam": (Sam, Sam_user),
  }


def _save_request(db, record_id, requester_id, **overrides):
  record = Request(
    id=record_id,
    title=overrides.pop("title", "Broken projector"),
    description=overrides.pop("description", "The projector in Room 4 is dead."),
    requester_id=requester_id,
    created_at=AT,
    updated_at=AT,
    **overrides,
  )
  requests_data.save(db, record)
  return record


def test_requester_creates_request_and_sees_it_in_client_view(cast, db):
  Mara, Mara_user = cast["Mara"]
  response = Mara.post(
    "/requests",
    data={
      "title": "New chairs",
      "description": "Two chairs are broken.",
      "domains": "Facilities, Room 4",
      "visibility": "PRIVATE",
      "priority_suggestion": "HIGH",
    },
  )
  assert response.status_code == 302
  assert "/requests/1" in response.headers["Location"]

  detail = Mara.get("/requests/1")
  assert detail.status_code == 200
  assert b"New chairs" in detail.data
  assert b"Open" in detail.data

  mine = Mara.get("/requests")
  assert b"New chairs" in mine.data
  assert b"New, not yet reviewed" in mine.data

  saved = requests_data.get(db, 1)
  assert saved.requester_id == Mara_user.id
  assert saved.priority_suggestion is Priority.HIGH


def test_private_records_stay_hidden_from_other_users(cast, db):
  Mara, Mara_user = cast["Mara"]
  junior, _ = cast["Sam"]
  _save_request(db, 1, Mara_user.id)
  issues_data.save(
    db,
    Issue(
      id=1,
      title="Secret outage",
      description="x",
      requester_id=Mara_user.id,
      created_at=AT,
      updated_at=AT,
    ),
  )
  assert Mara.get("/requests/1").status_code == 200
  assert junior.get("/requests/1").status_code == 404
  assert junior.get("/issues/1").status_code == 404
  assert b"Broken projector" not in junior.get("/requests").data


def test_request_transitions_follow_the_core(cast, db):
  admin, _ = cast["admin"]
  _, Mara_user = cast["Mara"]
  _save_request(db, 1, Mara_user.id)

  invalid = admin.post(
    "/requests/1/transition", data={"target": "FULFILLED"}, follow_redirects=True
  )
  assert b"cannot move" in invalid.data
  assert requests_data.get(db, 1).status.value == "OPEN"

  moved = admin.post("/requests/1/transition", data={"target": "PENDING"})
  assert moved.status_code == 302
  assert requests_data.get(db, 1).status.value == "PENDING"

  revoked = admin.post(
    "/requests/1/transition", data={"target": "REVOKED"}, follow_redirects=True
  )
  assert b"needs a reason" in revoked.data
  admin.post(
    "/requests/1/transition",
    data={"target": "REVOKED", "reason": "Duplicate of #9"},
  )
  assert requests_data.get(db, 1).status.value == "REVOKED"


def test_raise_creates_a_linked_issue(cast, db):
  admin, _ = cast["admin"]
  _, Mara_user = cast["Mara"]
  _save_request(
    db,
    1,
    Mara_user.id,
    status=RequestStatus.PENDING,
    priority_suggestion=Priority.URGENT,
    visibility=Visibility.PUBLIC,
  )
  response = admin.post("/requests/1/transition", data={"target": "RAISED"})
  assert "/issues/1" in response.headers["Location"]
  issue = issues_data.get(db, 1)
  assert issue.status is IssueStatus.OPEN
  assert issue.priority is Priority.URGENT
  assert issue.source_request_id == 1
  assert requests_data.get(db, 1).status.value == "RAISED"


def test_pending_edit_asks_for_confirmation_then_reopens(cast, db):
  Mara, Mara_user = cast["Mara"]
  _save_request(db, 1, Mara_user.id, status=RequestStatus.PENDING)
  ask = Mara.post(
    "/requests/1/edit",
    data={
      "title": "Brighter projector",
      "description": "Swap it for the laser unit.",
      "domains": "",
      "visibility": "PRIVATE",
      "priority_suggestion": "",
    },
  )
  assert b"back to Open" in ask.data
  assert requests_data.get(db, 1).title == "Broken projector"

  saved = Mara.post(
    "/requests/1/edit",
    data={
      "title": "Brighter projector",
      "description": "Swap it for the laser unit.",
      "domains": "",
      "visibility": "PRIVATE",
      "priority_suggestion": "",
      "confirmed": "1",
    },
  )
  assert saved.status_code == 302
  record = requests_data.get(db, 1)
  assert record.title == "Brighter projector"
  assert record.status is RequestStatus.OPEN


def test_comments_respect_core_permissions(cast, db):
  Mara, Mara_user = cast["Mara"]
  junior, _ = cast["Sam"]
  _save_request(db, 1, Mara_user.id)
  Mara.post("/requests/1/comment", data={"text": "Any update?"})
  detail = Mara.get("/requests/1")
  assert b"Any update?" in detail.data

  junior.post("/requests/1/comment", data={"text": "Sneaky"})
  assert b"Sneaky" not in Mara.get("/requests/1").data


def test_assignee_issue_flow_and_priority(cast, db):
  admin, _ = cast["admin"]
  Sam, Sam_user = cast["Sam"]
  _, Mara_user = cast["Mara"]
  issues_data.save(
    db,
    Issue(
      id=1,
      title="Fix the sink",
      description="It leaks.",
      requester_id=Mara_user.id,
      assignee_id=Sam_user.id,
      visibility=Visibility.PUBLIC,
      created_at=AT,
      updated_at=AT,
    ),
  )
  Sam.post("/issues/1/transition", data={"target": "BLOCKED"})
  assert issues_data.get(db, 1).status is IssueStatus.BLOCKED
  Sam.post("/issues/1/priority", data={"priority": "URGENT"})
  assert issues_data.get(db, 1).priority is Priority.URGENT
  board = Sam.get("/issues")
  assert b"Fix the sink" in board.data
  Sam.post("/issues/1/transition", data={"target": "OPEN"})
  Sam.post("/issues/1/transition", data={"target": "RESOLVED"})
  assert issues_data.get(db, 1).status is IssueStatus.RESOLVED

  admin.post(
    "/issues/1/edit",
    data={
      "title": "Fix the sink",
      "description": "It leaks.",
      "domains": "",
      "visibility": "PUBLIC",
      "priority": "LOW",
      "assignee_id": str(Sam_user.id),
    },
  )
  assert issues_data.get(db, 1).priority is Priority.LOW


def test_workspace_queues_counts_and_inspector(cast, db):
  admin, admin_user = cast["admin"]
  _, Mara_user = cast["Mara"]
  Sam, Sam_user = cast["Sam"]
  _save_request(db, 1, Mara_user.id, domains=("Facilities",))
  _save_request(db, 2, admin_user.id, title="Admin task")
  issues_data.save(
    db,
    Issue(
      id=1,
      title="Blocked door",
      description="x",
      status=IssueStatus.BLOCKED,
      requester_id=Mara_user.id,
      assignee_id=Sam_user.id,
      created_at=AT,
      updated_at=AT,
    ),
  )
  page = admin.get("/workspace")
  assert b"Needs triage" in page.data
  assert b"Broken projector" in page.data
  assert b"Blocked door" in page.data

  blocked = admin.get("/workspace?queue=blocked")
  assert b"Blocked door" in blocked.data
  facilities = admin.get("/workspace?queue=triage&domain=Facilities")
  assert b"Broken projector" in facilities.data
  assert b"Admin task" not in facilities.data

  junior_view = Sam.get("/workspace?queue=assigned")
  assert b"Blocked door" in junior_view.data
  assert Sam.get("/issues/1").status_code == 200

  pending = admin.get("/workspace?queue=triage&status=PENDING")
  assert b"Broken projector" not in pending.data


def test_two_new_requests_keep_their_own_numbers(cast, db):
  """The form writes the row SQLite numbered, so no request replaces another."""
  Mara, _ = cast["Mara"]
  first = Mara.post(
    "/requests",
    data={"title": "First chairs", "description": "Two chairs are broken."},
  )
  second = Mara.post(
    "/requests",
    data={"title": "Second chairs", "description": "One table is broken."},
  )
  assert first.status_code == 302 and second.status_code == 302
  assert first.headers["Location"] != second.headers["Location"]

  listed = Mara.get("/requests").data
  assert b"First chairs" in listed
  assert b"Second chairs" in listed


def test_a_failed_create_leaves_no_record(cast, db, monkeypatch):
  """One transaction: a failure after the row write leaves no half record."""
  from pwedepa.data import events as events_data

  Mara, _ = cast["Mara"]

  def fail(*args, **kwargs):
    raise RuntimeError("the event store is down")

  monkeypatch.setattr(events_data, "append", fail)
  response = Mara.post(
    "/requests", data={"title": "Half a record", "description": "Nothing stays."}
  )
  assert response.status_code == 500
  assert requests_data.list_requests(db) == []


def test_the_session_cookie_names_a_same_site_value(app):
  """A cross-site form post cannot ride on the session cookie."""
  assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
