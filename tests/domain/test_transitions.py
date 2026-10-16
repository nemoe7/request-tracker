from datetime import UTC, datetime

import pytest

from pwedepa.domain import (
  Actor,
  DomainError,
  Grant,
  Issue,
  IssueStatus,
  Priority,
  Request,
  RequestStatus,
  Visibility,
  raise_request,
  transition_issue,
  transition_request,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ADMIN = Actor(id=1, is_admin=True)
OWNER = Actor(id=2)
OTHER = Actor(id=3)


def make_request(status=RequestStatus.OPEN, **kwargs):
  fields = {
    "id": 10,
    "title": "Fix the gate",
    "description": "It sticks",
    "status": status,
    "requester_id": OWNER.id,
    "visibility": Visibility.PRIVATE,
    "created_at": NOW,
    "updated_at": NOW,
  }
  fields.update(kwargs)
  return Request(**fields)


def make_issue(status=IssueStatus.OPEN, **kwargs):
  fields = {
    "id": 20,
    "title": "Fix the gate",
    "description": "It sticks",
    "status": status,
    "requester_id": OWNER.id,
    "visibility": Visibility.PRIVATE,
    "created_at": NOW,
    "updated_at": NOW,
  }
  fields.update(kwargs)
  return Issue(**fields)


def test_new_request_starts_open_and_issue_defaults_to_high():
  assert make_request().status is RequestStatus.OPEN
  assert make_issue().priority is Priority.HIGH


def test_request_graph_allows_only_listed_moves():
  allowed = {
    (RequestStatus.OPEN, RequestStatus.PENDING),
    (RequestStatus.PENDING, RequestStatus.DELAYED),
    (RequestStatus.PENDING, RequestStatus.RAISED),
    (RequestStatus.DELAYED, RequestStatus.PENDING),
  }
  for current, target in allowed:
    result = transition_request(make_request(current), target, ADMIN, at=NOW)
    assert result.object.status is target
    assert result.events[0].event_type == "request.state_changed"
  for current in RequestStatus:
    for target in RequestStatus:
      if (current, target) in allowed or target is RequestStatus.REVOKED:
        continue
      if (
        current in (RequestStatus.OPEN, RequestStatus.PENDING, RequestStatus.DELAYED)
        and target
        in (
          RequestStatus.REJECTED,
          RequestStatus.FULFILLED,
        )
        and current is not RequestStatus.OPEN
      ):
        continue
      with pytest.raises(DomainError):
        transition_request(make_request(current), target, ADMIN, at=NOW)


def test_terminal_request_states_have_no_moves():
  for current in (
    RequestStatus.RAISED,
    RequestStatus.REJECTED,
    RequestStatus.FULFILLED,
    RequestStatus.REVOKED,
  ):
    with pytest.raises(DomainError):
      transition_request(make_request(current), RequestStatus.OPEN, ADMIN, at=NOW)


def test_revocation_needs_a_reason():
  with pytest.raises(DomainError):
    transition_request(make_request(), RequestStatus.REVOKED, OWNER, at=NOW)
  result = transition_request(
    make_request(), RequestStatus.REVOKED, OWNER, at=NOW, reason="no longer needed"
  )
  assert result.object.status is RequestStatus.REVOKED
  assert result.events[0].data["reason"] == "no longer needed"


def test_requester_cannot_raise_but_admin_can():
  pending = make_request(RequestStatus.PENDING)
  with pytest.raises(DomainError):
    transition_request(pending, RequestStatus.RAISED, OWNER, at=NOW)
  assert transition_request(pending, RequestStatus.RAISED, ADMIN, at=NOW)


def test_raise_copies_requester_visibility_and_domains():
  pending = make_request(
    RequestStatus.PENDING,
    visibility=Visibility.PUBLIC,
    domains=("hardware", "gate"),
    priority_suggestion=Priority.LOW,
  )
  raised, result = raise_request(pending, 99, ADMIN, at=NOW)
  assert raised.source_request_id == pending.id
  assert raised.requester_id == pending.requester_id
  assert raised.visibility is pending.visibility
  assert raised.domains == pending.domains
  assert raised.priority is Priority.LOW
  assert result.object.status is RequestStatus.RAISED


def test_raise_without_suggestion_uses_default_priority():
  raised, _ = raise_request(make_request(RequestStatus.PENDING), 99, ADMIN, at=NOW)
  assert raised.priority is Priority.HIGH


def test_issue_graph_and_requester_close_reopen():
  resolved = transition_issue(make_issue(), IssueStatus.RESOLVED, ADMIN, at=NOW).object
  closed = transition_issue(resolved, IssueStatus.CLOSED, OWNER, at=NOW).object
  assert closed.status is IssueStatus.CLOSED
  reopened = transition_issue(closed, IssueStatus.OPEN, OWNER, at=NOW).object
  assert reopened.status is IssueStatus.OPEN
  with pytest.raises(DomainError):
    transition_issue(make_issue(), IssueStatus.CLOSED, ADMIN, at=NOW)


def test_issue_block_cycle_needs_admin_or_assignee():
  with pytest.raises(DomainError):
    transition_issue(make_issue(), IssueStatus.BLOCKED, OTHER, at=NOW)
  assignee = Actor(id=9)
  issue = make_issue(assignee_id=assignee.id)
  assert transition_issue(issue, IssueStatus.BLOCKED, assignee, at=NOW)


def test_capability_grant_lets_a_requester_raise():
  raiser = Actor(id=4, grants=(Grant("request.raise"),))
  pending = make_request(RequestStatus.PENDING)
  result = transition_request(pending, RequestStatus.RAISED, raiser, at=NOW)
  assert result.object.status is RequestStatus.RAISED
