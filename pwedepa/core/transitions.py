"""Request and Issue state machines. Every move goes through these functions."""

from dataclasses import replace
from datetime import datetime

from .errors import CoreError, InvalidTransition, PermissionDenied
from .models import (
  Change,
  Event,
  Issue,
  IssueStatus,
  Priority,
  Request,
  RequestStatus,
)
from .permissions import Actor, authorize

REQUEST_TRANSITIONS = {
  RequestStatus.OPEN: (RequestStatus.PENDING, RequestStatus.REJECTED),
  RequestStatus.PENDING: (
    RequestStatus.DELAYED,
    RequestStatus.RAISED,
    RequestStatus.REJECTED,
    RequestStatus.FULFILLED,
  ),
  RequestStatus.DELAYED: (RequestStatus.PENDING, RequestStatus.REJECTED),
  RequestStatus.RAISED: (),
  RequestStatus.REJECTED: (),
  RequestStatus.FULFILLED: (),
}

ISSUE_TRANSITIONS = {
  IssueStatus.OPEN: (IssueStatus.BLOCKED, IssueStatus.RESOLVED),
  IssueStatus.BLOCKED: (IssueStatus.OPEN,),
  IssueStatus.RESOLVED: (IssueStatus.CLOSED, IssueStatus.OPEN),
  IssueStatus.CLOSED: (IssueStatus.OPEN,),
}

REQUEST_TARGET_VERBS = {
  RequestStatus.PENDING: "move",
  RequestStatus.DELAYED: "delay",
  RequestStatus.RAISED: "raise",
  RequestStatus.REJECTED: "reject",
  RequestStatus.FULFILLED: "fulfill",
}

ISSUE_TARGET_VERBS = {
  IssueStatus.BLOCKED: "block",
  IssueStatus.RESOLVED: "resolve",
  IssueStatus.CLOSED: "close",
}


def _issue_target_verb(issue: Issue, target: IssueStatus) -> str:
  if target is IssueStatus.OPEN:
    return (
      "reopen"
      if issue.status in (IssueStatus.RESOLVED, IssueStatus.CLOSED)
      else "unblock"
    )
  return ISSUE_TARGET_VERBS[target]


def _can_move_request(actor: Actor, request: Request, target: RequestStatus) -> bool:
  verb = REQUEST_TARGET_VERBS[target]
  return authorize(
    actor,
    f"request.{verb}",
    object_id=request.id,
    owner_id=request.requester_id,
    visibility=request.visibility,
  )


def _can_move_issue(actor: Actor, issue: Issue, target: IssueStatus) -> bool:
  verb = _issue_target_verb(issue, target)
  if authorize(
    actor,
    f"issue.{verb}",
    object_id=issue.id,
    owner_id=issue.requester_id,
    visibility=issue.visibility,
  ):
    return True
  if actor.id is not None and actor.id == issue.assignee_id:
    return verb in ("block", "unblock", "resolve")
  return False


def transition_request(
  request: Request,
  target: RequestStatus,
  actor: Actor,
  *,
  at: datetime,
  reason: str | None = None,
) -> Change:
  if target not in REQUEST_TRANSITIONS[request.status]:
    raise InvalidTransition(
      f"A request cannot go from {request.status.value.capitalize()} to "
      f"{target.value.capitalize()}."
    )
  if target is RequestStatus.REJECTED and not reason:
    raise CoreError("Give a reason to reject.")
  if not _can_move_request(actor, request, target):
    raise PermissionDenied(
      f"You cannot move this request to {target.value.capitalize()}."
    )
  moved = replace(request, status=target, updated_at=at)
  data = {"from": request.status.value, "to": target.value}
  if reason:
    data["reason"] = reason
  event = Event("request.state_changed", actor.id, at, data)
  return Change(moved, (event,))


def transition_issue(
  issue: Issue,
  target: IssueStatus,
  actor: Actor,
  *,
  at: datetime,
) -> Change:
  if target not in ISSUE_TRANSITIONS[issue.status]:
    raise InvalidTransition(
      f"An issue cannot go from {issue.status.value.capitalize()} to "
      f"{target.value.capitalize()}."
    )
  if not _can_move_issue(actor, issue, target):
    raise PermissionDenied(
      f"You cannot move this issue to {target.value.capitalize()}."
    )
  moved = replace(issue, status=target, updated_at=at)
  event = Event(
    "issue.state_changed",
    actor.id,
    at,
    {"from": issue.status.value, "to": target.value},
  )
  return Change(moved, (event,))


def raise_request(
  request: Request,
  actor: Actor,
  *,
  at: datetime,
) -> tuple[Issue, Change]:
  """New Issues start without an id. Callers write an event naming each id."""
  change = transition_request(request, RequestStatus.RAISED, actor, at=at)
  issue = Issue(
    id=0,
    title=request.title,
    description=request.description,
    source_request_id=request.id,
    requester_id=request.requester_id,
    priority=request.priority_suggestion or Priority.HIGH,
    visibility=request.visibility,
    domains=request.domains,
    created_at=at,
    updated_at=at,
  )
  return issue, change
