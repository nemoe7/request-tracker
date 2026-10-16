from datetime import UTC, datetime

import pytest

from pwedepa.core import (
  Event,
  Issue,
  IssueStatus,
  Priority,
  Request,
  RequestStatus,
  Visibility,
)
from pwedepa.data import db as data_db
from pwedepa.data import events, issues, requests

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
  connection = data_db.connect(tmp_path / "test.db")
  yield connection
  connection.close()


def make_request(**overrides):
  values = {
    "id": 1,
    "title": "Fix the sink",
    "description": "It leaks",
    "status": RequestStatus.PENDING,
    "requester_id": 7,
    "priority_suggestion": Priority.HIGH,
    "priority_unsure": True,
    "visibility": Visibility.PUBLIC,
    "domains": ("home", "plumbing"),
    "created_at": AT,
    "updated_at": AT,
  }
  values.update(overrides)
  return Request(**values)


def make_issue(**overrides):
  values = {
    "id": 1,
    "title": "Sink is broken",
    "description": "Raised from a request",
    "status": IssueStatus.BLOCKED,
    "source_request_id": 1,
    "requester_id": 7,
    "assignee_id": 9,
    "priority": Priority.URGENT,
    "visibility": Visibility.PRIVATE,
    "domains": ("home",),
    "created_at": AT,
    "updated_at": AT,
  }
  values.update(overrides)
  return Issue(**values)


def test_request_round_trip(db):
  requests.save(db, make_request())
  assert requests.get(db, 1) == make_request()


def test_issue_round_trip(db):
  issues.save(db, make_issue())
  assert issues.get(db, 1) == make_issue()


def test_save_updates_in_place(db):
  requests.save(db, make_request())
  requests.save(db, make_request(title="Fix the tap", updated_at=LATER))
  loaded = requests.get(db, 1)
  assert loaded.title == "Fix the tap"
  assert loaded.updated_at == LATER
  assert len(requests.list_requests(db)) == 1


def test_get_missing_returns_none(db):
  assert requests.get(db, 99) is None
  assert issues.get(db, 99) is None


def test_defaults_round_trip(db):
  requests.save(db, Request(id=2, title="Bare", description=""))
  loaded = requests.get(db, 2)
  assert loaded.status is RequestStatus.OPEN
  assert loaded.priority_suggestion is None
  assert loaded.domains == ()
  issues.save(db, Issue(id=2, title="Bare", description=""))
  assert issues.get(db, 2).priority is Priority.HIGH


def test_list_filters(db):
  requests.save(db, make_request())
  requests.save(
    db, make_request(id=2, status=RequestStatus.OPEN, requester_id=8, domains=("work",))
  )
  assert [r.id for r in requests.list_requests(db, status=RequestStatus.OPEN)] == [2]
  assert [r.id for r in requests.list_requests(db, requester_id=7)] == [1]
  assert [r.id for r in requests.list_requests(db, domain="work")] == [2]
  issues.save(db, make_issue())
  issues.save(db, make_issue(id=2, assignee_id=10))
  assert [i.id for i in issues.list_issues(db, assignee_id=10)] == [2]
  assert [i.id for i in issues.list_issues(db, status=IssueStatus.BLOCKED)] == [1, 2]


def test_soft_delete_visibility(db):
  requests.save(db, make_request(deleted_at=LATER))
  assert requests.list_requests(db) == []
  assert [r.id for r in requests.list_requests(db, include_deleted=True)] == [1]
  assert requests.get(db, 1).deleted_at == LATER


def test_events_round_trip(db):
  first = Event(
    event_type="request.created", actor_id=7, at=AT, data={"title": "Fix the sink"}
  )
  second = Event(
    event_type="request.moved", actor_id=9, at=LATER, data={"from": "OPEN"}
  )
  events.append(db, "request", 1, first)
  events.append(db, "request", 1, second)
  events.append(db, "issue", 1, first)
  assert events.list_for(db, "request", 1) == [first, second]
  assert events.list_for(db, "issue", 1) == [first]


def test_initialize_is_idempotent(db):
  data_db.initialize(db)
  data_db.initialize(db)
  tables = {
    row[0]
    for row in db.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'")
  }
  assert {
    "users",
    "user_roles",
    "permission_grants",
    "passkeys",
    "webauthn_challenges",
    "enrollment_tokens",
    "sessions",
    "audit_events",
  } <= tables
  requests.save(db, make_request())
  assert requests.get(db, 1).title == "Fix the sink"


def test_a_saved_request_takes_the_id_sqlite_assigns(db):
  """Two records saved as new keep their own rows, even at the same moment."""
  first = requests.save(db, make_request(id=0, title="First"))
  second = requests.save(db, make_request(id=0, title="Second"))

  assert first.id and second.id
  assert first.id != second.id
  assert requests.get(db, first.id).title == "First"
  assert requests.get(db, second.id).title == "Second"


def test_a_saved_issue_takes_the_id_sqlite_assigns(db):
  first = issues.save(db, Issue(id=0, title="First", description=""))
  second = issues.save(db, Issue(id=0, title="Second", description=""))

  assert first.id and second.id
  assert first.id != second.id
  assert issues.get(db, first.id).title == "First"
  assert issues.get(db, second.id).title == "Second"


def test_a_database_file_prepares_its_schema_once(tmp_path, monkeypatch):
  """The schema must run when a file first opens, not on every request."""
  calls = []
  real_initialize = data_db.initialize

  def count(connection):
    calls.append(connection)
    real_initialize(connection)

  monkeypatch.setattr(data_db, "initialize", count)
  path = tmp_path / "once.db"

  data_db.connect(path).close()
  data_db.connect(path).close()

  assert len(calls) == 1
