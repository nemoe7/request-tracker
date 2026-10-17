from datetime import UTC, datetime

import pytest
from _paths import record_url

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
from pwedepa.data import events as events_data
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
  assert record_url(1) in response.headers["Location"]

  saved = requests_data.get(db, 1)
  detail = Mara.get(record_url(1))
  assert detail.status_code == 200
  assert saved.title.encode() in detail.data
  assert saved.status is RequestStatus.OPEN

  mine = Mara.get("/requests")
  assert record_url(1).encode() in mine.data
  assert saved.title.encode() in mine.data
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
  assert Mara.get(record_url(1)).status_code == 200
  assert junior.get(record_url(1)).status_code == 404
  assert junior.get(record_url(1, "issues")).status_code == 404
  assert requests_data.get(db, 1).title.encode() not in junior.get("/requests").data


def test_request_transitions_follow_the_core(cast, db):
  admin, _ = cast["admin"]
  _, Mara_user = cast["Mara"]
  _save_request(db, 1, Mara_user.id)

  invalid = admin.post("/requests/1/transition", data={"target": "FULFILLED"})
  assert invalid.status_code == 302
  assert requests_data.get(db, 1).status.value == "OPEN"

  moved = admin.post("/requests/1/transition", data={"target": "PENDING"})
  assert moved.status_code == 302
  assert requests_data.get(db, 1).status.value == "PENDING"

  revoked = admin.post("/requests/1/transition", data={"target": "REVOKED"})
  assert revoked.status_code == 302
  assert requests_data.get(db, 1).status.value == "PENDING"
  admin.post(
    "/requests/1/transition",
    data={"target": "REVOKED", "reason": "Duplicate of #9"},
  )
  assert requests_data.get(db, 1).status.value == "REVOKED"


def test_a_value_the_page_cannot_send_gets_a_sentence(cast, db):
  """A crafted form value must not turn into an error page."""
  admin, _ = cast["admin"]
  _, Mara_user = cast["Mara"]
  _save_request(db, 1, Mara_user.id)

  move = admin.post("/requests/1/transition", data={"target": "BOGUS"})
  assert move.status_code == 302
  assert requests_data.get(db, 1).status.value == "OPEN"

  created = admin.post(
    "/requests",
    data={"title": "Chairs", "visibility": "BOGUS", "priority_suggestion": "BOGUS"},
  )
  assert created.status_code == 302
  saved = requests_data.get(db, 1)
  assert saved.visibility is Visibility.PRIVATE
  assert saved.priority_suggestion is None

  edited = admin.post(
    "/requests/1/edit",
    data={
      "title": "Broken projector",
      "description": "The projector in Room 4 is dead.",
      "visibility": "BOGUS",
      "domains": "",
      "priority_suggestion": "BOGUS",
    },
  )
  assert edited.status_code == 302
  assert requests_data.get(db, 1).visibility is Visibility.PRIVATE


def test_an_edit_keeps_the_fields_a_value_cannot_change(cast, db):
  """Text the page cannot send leaves a field alone. An empty priority still clears it."""
  admin, _ = cast["admin"]
  _, Mara_user = cast["Mara"]
  _save_request(
    db, 1, Mara_user.id, visibility=Visibility.PUBLIC, priority_suggestion=Priority.HIGH
  )

  junk = admin.post(
    "/requests/1/edit",
    data={
      "title": "Broken projector",
      "description": "The projector in Room 4 is dead.",
      "visibility": "BOGUS",
      "domains": "",
      "priority_suggestion": "BOGUS",
    },
  )
  assert junk.status_code == 302
  kept = requests_data.get(db, 1)
  assert kept.visibility is Visibility.PUBLIC
  assert kept.priority_suggestion is Priority.HIGH

  cleared = admin.post(
    "/requests/1/edit",
    data={
      "title": "Broken projector",
      "description": "The projector in Room 4 is dead.",
      "visibility": "PUBLIC",
      "domains": "",
      "priority_suggestion": "",
    },
  )
  assert cleared.status_code == 302
  assert requests_data.get(db, 1).priority_suggestion is None


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
  assert record_url(1, "issues") in response.headers["Location"]
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
  assert ask.status_code == 200
  assert requests_data.get(db, 1).title != "Brighter projector"

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
  detail = Mara.get(record_url(1))
  comments = [
    event
    for event in events_data.list_for(db, "request", 1)
    if event.event_type == "request.comment"
  ]
  assert len(comments) == 1
  assert comments[0].data["text"].encode() in detail.data

  junior.post("/requests/1/comment", data={"text": "Sneaky"})
  refused = [
    event
    for event in events_data.list_for(db, "request", 1)
    if event.event_type == "request.comment"
  ]
  assert len(refused) == 1


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
  assert issues_data.get(db, 1).title.encode() in board.data
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
  mine = _save_request(db, 1, Mara_user.id, domains=("Facilities",))
  other = _save_request(db, 2, admin_user.id, title="Admin task")
  issue = issues_data.save(
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
  page = admin.get("/")
  assert b"queue=triage" in page.data
  assert mine.title.encode() in page.data
  assert issue.title.encode() not in page.data, "the requests list carries no issue"

  blocked = admin.get("/?queue=blocked")
  assert issue.title.encode() in blocked.data
  facilities = admin.get("/?queue=triage&domain=Facilities")
  assert mine.title.encode() in facilities.data
  assert other.title.encode() not in facilities.data

  junior_view = Sam.get("/?queue=assigned")
  assert issue.title.encode() in junior_view.data
  assert Sam.get(record_url(1, "issues")).status_code == 200

  pending = admin.get("/?queue=triage&status=PENDING")
  assert mine.title.encode() not in pending.data


def test_the_workspace_holds_no_my_requests_queue(cast, db):
  admin, admin_user = cast["admin"]
  _save_request(db, 1, admin_user.id, domains=("Facilities",))

  page = admin.get("/")

  assert b"queue=mine" not in page.data, "the queue drops its own-requests filter"
  stale = admin.get("/?queue=mine")
  assert stale.status_code == 200, "an old link still opens the list"


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
  assert record_url(1).encode() in listed
  assert record_url(2).encode() in listed


def test_a_failed_create_leaves_no_record(cast, db, monkeypatch):
  """One transaction: a failure after the row write leaves no half-written row."""
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
