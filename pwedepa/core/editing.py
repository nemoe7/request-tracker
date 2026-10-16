"""Field edits for Requests and Issues. Identity fields never change here."""

from dataclasses import replace
from datetime import datetime

from .errors import ConfirmationRequired, CoreError, PermissionDenied
from .models import Change, Event, Issue, IssueStatus, Request, RequestStatus
from .permissions import Actor, authorize

REQUEST_FIELDS = {
  "title",
  "description",
  "visibility",
  "domains",
  "priority_suggestion",
  "priority_unsure",
}
ISSUE_FIELDS = {
  "title",
  "description",
  "visibility",
  "domains",
  "priority",
  "assignee_id",
}


def _check_fields(fields: dict, allowed: set) -> None:
  unknown = sorted(set(fields) - allowed)
  if unknown:
    raise CoreError(f"fields cannot change here: {', '.join(unknown)}")


def _is_editable(request: Request) -> bool:
  return request.status not in (
    RequestStatus.RAISED,
    RequestStatus.REJECTED,
    RequestStatus.FULFILLED,
    RequestStatus.REVOKED,
  )


def edit_request(
  request: Request,
  actor: Actor,
  *,
  at: datetime,
  confirmed: bool = False,
  **fields,
) -> Change:
  """Edit a Request. A requester edit of a pending Request returns it to OPEN."""
  if not fields:
    raise CoreError("an edit needs at least one field")
  _check_fields(fields, REQUEST_FIELDS)
  if request.deleted_at is not None:
    raise CoreError("a deleted request cannot be edited")
  if not REQUEST_TRANSITIONS_OPEN(request):
    raise CoreError("a request in a terminal state cannot be edited")
  if not authorize(
    actor,
    "request.edit",
    object_id=request.id,
    owner_id=request.requester_id,
    visibility=request.visibility,
  ):
    raise PermissionDenied("actor cannot edit this request")
  by_requester = actor.id is not None and actor.id == request.requester_id
  if request.status is RequestStatus.PENDING and by_requester and not confirmed:
    raise ConfirmationRequired("editing a pending request returns it to OPEN")
  status = request.status
  if request.status is RequestStatus.PENDING and by_requester:
    status = RequestStatus.OPEN
  edited = replace(request, **fields, status=status, updated_at=at)
  event = Event("request.edited", actor.id, at, {"fields": sorted(fields)})
  return Change(edited, (event,))


def REQUEST_TRANSITIONS_OPEN(request: Request) -> bool:
  return request.status not in (
    RequestStatus.RAISED,
    RequestStatus.REJECTED,
    RequestStatus.FULFILLED,
    RequestStatus.REVOKED,
  )


def edit_issue(
  issue: Issue,
  actor: Actor,
  *,
  at: datetime,
  **fields,
) -> Change:
  """Edit an Issue. Only an admin reassigns. A priority change is its own event."""
  if not fields:
    raise CoreError("an edit needs at least one field")
  _check_fields(fields, ISSUE_FIELDS)
  if issue.deleted_at is not None:
    raise CoreError("a deleted issue cannot be edited")
  if issue.status is IssueStatus.CLOSED:
    raise CoreError("a closed issue cannot be edited")
  if (
    "assignee_id" in fields
    and not actor.is_admin
    and not authorize(
      actor, "issue.edit", object_id=issue.id, owner_id=issue.requester_id
    )
  ):
    raise PermissionDenied("actor cannot reassign an issue")
  is_assignee = actor.id is not None and actor.id == issue.assignee_id
  others = {name: value for name, value in fields.items() if name != "priority"}
  if others and not (
    actor.is_admin
    or authorize(actor, "issue.edit", object_id=issue.id, owner_id=issue.requester_id)
  ):
    raise PermissionDenied("actor cannot edit this issue")
  if "priority" in fields and not (
    actor.is_admin
    or is_assignee
    or (actor.id is not None and actor.id == issue.requester_id)
    or authorize(actor, "issue.edit", object_id=issue.id, owner_id=issue.requester_id)
  ):
    raise PermissionDenied("actor cannot change this issue priority")
  edited = replace(issue, **fields, updated_at=at)
  events = []
  if "priority" in fields and fields["priority"] is not issue.priority:
    events.append(
      Event(
        "issue.priority_changed",
        actor.id,
        at,
        {"from": issue.priority.value, "to": fields["priority"].value},
      )
    )
  if others:
    events.append(Event("issue.edited", actor.id, at, {"fields": sorted(others)}))
  if not events:
    events.append(Event("issue.edited", actor.id, at, {"fields": []}))
  return Change(edited, tuple(events))
