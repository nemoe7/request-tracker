from datetime import UTC, datetime

import pytest

from pwedepa.domain import (
  Actor,
  ConfirmationRequired,
  DomainError,
  Issue,
  IssueStatus,
  Request,
  RequestStatus,
  Visibility,
  edit_issue,
  edit_request,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
LATER = datetime(2026, 1, 2, tzinfo=UTC)
ADMIN = Actor(id=1, is_admin=True)
OWNER = Actor(id=2)
OTHER = Actor(id=3)


def make_request(status=RequestStatus.OPEN):
  return Request(
    id=10,
    title="Old title",
    description="Old body",
    status=status,
    requester_id=OWNER.id,
    visibility=Visibility.PRIVATE,
    created_at=NOW,
    updated_at=NOW,
  )


def make_issue():
  return Issue(
    id=20,
    title="Old title",
    description="Old body",
    status=IssueStatus.OPEN,
    requester_id=OWNER.id,
    created_at=NOW,
    updated_at=NOW,
  )


def test_owner_edits_own_open_request():
  result = edit_request(make_request(), OWNER, at=LATER, title="New title")
  assert result.object.title == "New title"
  assert result.object.status is RequestStatus.OPEN
  assert result.object.updated_at == LATER
  assert result.events[0].event_type == "request.edited"


def test_pending_edit_needs_confirmation_and_returns_to_open():
  pending = make_request(RequestStatus.PENDING)
  with pytest.raises(ConfirmationRequired):
    edit_request(pending, OWNER, at=LATER, title="New title")
  result = edit_request(pending, OWNER, at=LATER, title="New title", confirmed=True)
  assert result.object.status is RequestStatus.OPEN


def test_other_user_cannot_edit_and_requester_id_never_changes():
  with pytest.raises(DomainError):
    edit_request(make_request(), OTHER, at=LATER, title="New title")
  with pytest.raises(DomainError):
    edit_request(make_request(), ADMIN, at=LATER, requester_id=99)


def test_terminal_request_cannot_be_edited():
  with pytest.raises(DomainError):
    edit_request(make_request(RequestStatus.REJECTED), ADMIN, at=LATER, title="New")


def test_admin_assigns_an_issue_and_priority_change_is_an_event():
  result = edit_issue(make_issue(), ADMIN, at=LATER, assignee_id=7)
  assert result.object.assignee_id == 7
  from pwedepa.domain import Priority

  assigned = edit_issue(make_issue(), ADMIN, at=LATER, assignee_id=7).object
  changed = edit_issue(assigned, Actor(id=7), at=LATER, priority=Priority.URGENT)
  assert changed.object.priority is Priority.URGENT
  assert changed.events[0].event_type == "issue.priority_changed"


def test_assignee_cannot_reassign():
  with pytest.raises(DomainError):
    edit_issue(make_issue(), Actor(id=7), at=LATER, assignee_id=8)


def test_assignee_cannot_change_visibility():
  assigned = edit_issue(make_issue(), ADMIN, at=LATER, assignee_id=7).object
  with pytest.raises(DomainError):
    edit_issue(assigned, Actor(id=7), at=LATER, visibility=Visibility.PUBLIC)
