"""Request and Issue pages. Every write routes through the core rules."""

from flask import (
  Blueprint,
  abort,
  flash,
  redirect,
  render_template,
  request,
  session,
  url_for,
)
from werkzeug.wrappers import Response

from pwedepa.auth import Role, actor_for_user, list_roles, list_users
from pwedepa.core import (
  Actor,
  ConfirmationRequired,
  CoreError,
  Event,
  Grant,
  IssueStatus,
  Priority,
  Request,
  RequestStatus,
  Visibility,
  authorize,
  edit_issue,
  edit_request,
  raise_request,
  transition_issue,
  transition_request,
)
from pwedepa.core.transitions import ISSUE_TRANSITIONS, REQUEST_TRANSITIONS
from pwedepa.data import events as events_data
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import requests as requests_data
from pwedepa.data import sharing as sharing_data
from pwedepa.data.db import transaction

from .. import now
from ._helpers import can_share, current_user, db

bp = Blueprint("records", __name__)

REQUEST_LABELS = {
  RequestStatus.PENDING: "Move to pending",
  RequestStatus.DELAYED: "Delay",
  RequestStatus.RAISED: "Raise to issue",
  RequestStatus.REJECTED: "Reject",
  RequestStatus.FULFILLED: "Fulfill",
  RequestStatus.REVOKED: "Revoke",
}
STATUS_WORDS = {
  RequestStatus.OPEN: "New, not yet reviewed",
  RequestStatus.PENDING: "Waiting for review",
  RequestStatus.DELAYED: "Delayed",
  RequestStatus.RAISED: "Turned into work",
  RequestStatus.REJECTED: "Not accepted",
  RequestStatus.FULFILLED: "Done",
  RequestStatus.REVOKED: "Withdrawn",
}


def _user():
  user = current_user()
  if user is None:
    return None
  return user


def _actor(user):
  return actor_for_user(db(), user.id)


def _names() -> dict[int, str]:
  return {
    user.id: user.display_name for user in list_users(db(), include_archived=True)
  }


def _can(actor, action: str, record) -> bool:
  return authorize(
    actor,
    action,
    object_id=record.id,
    owner_id=record.requester_id,
    visibility=record.visibility,
  )


def _actor_for_record(actor, object_type: str, record):
  """Add the active share link grants for one record to an actor."""
  link_id = session.get("share_link_id")
  if not link_id:
    return actor
  link = sharing_data.get(db(), link_id)
  if link is None or not sharing_data.is_active(link, now()):
    return actor
  if link.object_type != object_type or link.object_id != record.id:
    return actor
  grants = [Grant(f"{object_type}.{record.id}.view")]
  if "COMMENT" in link.permissions:
    grants.append(Grant(f"{object_type}.{record.id}.comment"))
  if "EDIT" in link.permissions:
    grants.append(Grant(f"{object_type}.{record.id}.edit"))
  return Actor(actor.id, actor.is_admin, actor.grants + tuple(grants))


def _viewable_requests(actor, rows) -> list:
  return [
    row
    for row in rows
    if _can(_actor_for_record(actor, "request", row), "request.view", row)
  ]


def _can_view_issue(actor, record) -> bool:
  # The core lets an assignee work an issue. Seeing it comes with the job.
  if actor.id is not None and actor.id == record.assignee_id:
    return True
  return _can(actor, "issue.view", record)


def _viewable_issues(actor, rows) -> list:
  return [
    row for row in rows if _can_view_issue(_actor_for_record(actor, "issue", row), row)
  ]


def _can_comment_issue(actor, record) -> bool:
  if actor.id is not None and actor.id == record.assignee_id:
    return True
  return _can(actor, "issue.comment", record)


def _issued_token(object_type: str, object_id: int) -> str | None:
  stored = session.get("issued_share")
  if not stored:
    return None
  if stored.get("object_type") != object_type or stored.get("object_id") != object_id:
    return None
  session.pop("issued_share", None)
  return stored.get("token")


def _event_message(record, event) -> str:
  if event.event_type.endswith("state_changed"):
    return f"{record.title}: {event.data.get('from', '')} to {event.data.get('to', '')}"
  if event.event_type.endswith("comment"):
    return f"New comment on {record.title}"
  if event.event_type.endswith("priority_changed"):
    return (
      f"{record.title}: priority {event.data.get('from', '')} "
      f"to {event.data.get('to', '')}"
    )
  if event.event_type.endswith("raised_from_request"):
    return f"{record.title} was raised into Issue #{event.data.get('issue_id', '')}"
  if event.event_type.endswith("created"):
    return f"New record: {record.title}"
  if event.event_type.endswith("edited"):
    return f"{record.title} was edited"
  return f"{record.title}: {event.event_type.replace('.', ' ')}"


def _notify_event(object_type: str, record, event, *, commit: bool = True) -> None:
  if event.event_type.endswith("comment"):
    category = "comments"
  elif "share" in event.event_type:
    category = "sharing"
  else:
    category = "activity"
  recipients = {record.requester_id}
  if object_type == "issue":
    recipients.add(record.assignee_id)
  for user_id in recipients:
    if user_id is None or user_id == event.actor_id:
      continue
    notifications_data.notify(
      db(),
      user_id,
      category,
      _event_message(record, event),
      at=now(),
      commit=commit,
      object_type=object_type,
      object_id=record.id,
      actor_id=event.actor_id,
    )


def _append_all(object_type: str, record, change, *, commit: bool = True) -> None:
  for event in change.events:
    events_data.append(db(), object_type, record.id, event, commit=commit)
    _notify_event(object_type, record, event, commit=commit)


def _request_actions(actor, record) -> list[tuple[str, str]]:
  actions = []
  for target in REQUEST_TRANSITIONS[record.status]:
    verb = {
      RequestStatus.PENDING: "move",
      RequestStatus.DELAYED: "delay",
      RequestStatus.RAISED: "raise",
      RequestStatus.REJECTED: "reject",
      RequestStatus.FULFILLED: "fulfill",
      RequestStatus.REVOKED: "revoke",
    }[target]
    if _can(actor, f"request.{verb}", record):
      actions.append((target.value, REQUEST_LABELS[target]))
  return actions


def _issue_actions(actor, record) -> list[tuple[str, str]]:
  actions = []
  for target in ISSUE_TRANSITIONS[record.status]:
    if target is IssueStatus.OPEN:
      verb = (
        "reopen"
        if record.status in (IssueStatus.RESOLVED, IssueStatus.CLOSED)
        else "unblock"
      )
      label = "Reopen" if verb == "reopen" else "Unblock"
    else:
      verb = {
        IssueStatus.BLOCKED: "block",
        IssueStatus.RESOLVED: "resolve",
        IssueStatus.CLOSED: "close",
      }[target]
      label = verb.capitalize()
    allowed = _can(actor, f"issue.{verb}", record)
    if not allowed and actor.id is not None and actor.id == record.assignee_id:
      allowed = verb in ("block", "unblock", "resolve")
    if allowed:
      actions.append((target.value, label))
  return actions


def _load_request(actor, request_id: int):
  record = requests_data.get(db(), request_id)
  if record is None:
    abort(404)
  actor = _actor_for_record(actor, "request", record)
  if not _can(actor, "request.view", record):
    abort(404)
  return record, actor


def _load_issue(actor, issue_id: int):
  record = issues_data.get(db(), issue_id)
  if record is None:
    abort(404)
  actor = _actor_for_record(actor, "issue", record)
  if not _can_view_issue(actor, record):
    abort(404)
  return record, actor


@bp.get("/workspace")
def workspace() -> str | Response:
  """Show the staff work queue with filters, records, and an inspector."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not is_staff(user):
    return redirect(url_for("records.requests"))
  actor = _actor(user)
  queue = request.args.get("queue", "triage")
  domain = request.args.get("domain", "")
  visibility = request.args.get("visibility", "")
  status_filter = request.args.get("status", "")

  all_requests = _viewable_requests(actor, requests_data.list_requests(db()))
  all_issues = _viewable_issues(actor, issues_data.list_issues(db()))

  def in_domain(record) -> bool:
    return not domain or domain in record.domains

  def in_visibility(record) -> bool:
    return not visibility or record.visibility.value == visibility

  def in_status(record) -> bool:
    return not status_filter or record.status.value == status_filter

  counts = {
    "triage": sum(1 for r in all_requests if r.status is RequestStatus.OPEN),
    "mine": sum(1 for r in all_requests if r.requester_id == user.id),
    "assigned": sum(1 for i in all_issues if i.assignee_id == user.id),
    "blocked": sum(1 for i in all_issues if i.status is IssueStatus.BLOCKED),
    "public": sum(1 for r in all_requests if r.visibility is Visibility.PUBLIC),
  }
  if queue == "assigned":
    rows = [
      i
      for i in all_issues
      if i.assignee_id == user.id and in_domain(i) and in_status(i)
    ]
    row_kind = "issue"
  elif queue == "blocked":
    rows = [
      i
      for i in all_issues
      if i.status is IssueStatus.BLOCKED and in_domain(i) and in_status(i)
    ]
    row_kind = "issue"
  else:
    rows = [
      r for r in all_requests if in_domain(r) and in_visibility(r) and in_status(r)
    ]
    if queue == "triage":
      rows = [r for r in rows if r.status is RequestStatus.OPEN]
    elif queue == "mine":
      rows = [r for r in rows if r.requester_id == user.id]
    elif queue == "public":
      rows = [r for r in rows if r.visibility is Visibility.PUBLIC]
    row_kind = "request"

  selected = None
  selected_id = request.args.get("selected", type=int)
  if row_kind == "request" and selected_id:
    selected = next((r for r in rows if r.id == selected_id), None)
  board = {
    status: [i for i in all_issues if i.status is status and in_domain(i)]
    for status in (
      IssueStatus.OPEN,
      IssueStatus.BLOCKED,
      IssueStatus.RESOLVED,
      IssueStatus.CLOSED,
    )
  }
  domains = sorted({d for r in all_requests + all_issues for d in r.domains})
  return render_template(
    "workspace.html",
    queue=queue,
    domain=domain,
    visibility=visibility,
    status_filter=status_filter,
    statuses=[status.value for status in RequestStatus]
    + [status.value for status in IssueStatus if status is not IssueStatus.OPEN],
    domains=domains,
    counts=counts,
    rows=rows,
    row_kind=row_kind,
    board=board,
    selected=selected,
    selected_actions=_request_actions(actor, selected) if selected else [],
    selected_events=(
      events_data.list_for(db(), "request", selected.id)[-2:] if selected else []
    ),
    names=_names(),
  )


@bp.get("/requests")
def requests() -> str | Response:
  """Show the client view: the signed-in requests and the public board."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  all_requests = _viewable_requests(actor, requests_data.list_requests(db()))
  mine = [r for r in all_requests if r.requester_id == user.id]
  public = [
    r
    for r in all_requests
    if r.visibility is Visibility.PUBLIC and r.requester_id != user.id
  ]
  return render_template(
    "requests.html", mine=mine, public=public, status_words=STATUS_WORDS, names=_names()
  )


@bp.get("/requests/new")
def request_new() -> str | Response:
  """Show the create-request form."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not authorize(_actor(user), "request.create"):
    flash("Your account cannot create requests.")
    return redirect(url_for("records.requests"))
  return render_template(
    "request_form.html", record=None, priorities=[p.value for p in Priority]
  )


@bp.post("/requests")
def request_create() -> Response:
  """Create a request from the submitted form."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  if not authorize(actor, "request.create"):
    flash("Your account cannot create requests.")
    return redirect(url_for("records.requests"))
  title = request.form.get("title", "").strip()
  if not title:
    flash("A request needs a title.")
    return redirect(url_for("records.request_new"))
  at = now()
  priority = request.form.get("priority_suggestion", "")
  with transaction(db()):
    record = requests_data.save(
      db(),
      Request(
        id=0,
        title=title,
        description=request.form.get("description", "").strip(),
        requester_id=user.id,
        priority_suggestion=Priority(priority) if priority else None,
        priority_unsure="priority_unsure" in request.form,
        visibility=Visibility(request.form.get("visibility", "PRIVATE")),
        domains=tuple(
          part.strip()
          for part in request.form.get("domains", "").split(",")
          if part.strip()
        ),
        created_at=at,
        updated_at=at,
      ),
      commit=False,
    )
    created = Event("request.created", user.id, at)
    events_data.append(db(), "request", record.id, created, commit=False)
    _notify_event("request", record, created, commit=False)
  return redirect(url_for("records.request_detail", request_id=record.id))


@bp.get("/requests/<int:request_id>")
def request_detail(request_id: int) -> str | Response:
  """Show one request with facts, activity, comments, and actions."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  events = events_data.list_for(db(), "request", request_id)
  return render_template(
    "request_detail.html",
    record=record,
    actions=_request_actions(actor, record),
    can_edit=_can(actor, "request.edit", record),
    can_comment=_can(actor, "request.comment", record),
    events=events,
    comments=[e for e in events if e.event_type == "request.comment"],
    share_links=sharing_data.list_for_object(db(), "request", record.id),
    can_share=can_share(user, record),
    object_type="request",
    issued_token=_issued_token("request", record.id),
    names=_names(),
  )


@bp.post("/requests/<int:request_id>/transition")
def request_transition(request_id: int) -> Response:
  """Run one request state move through the core."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  target = RequestStatus(request.form["target"])
  at = now()
  try:
    if target is RequestStatus.RAISED:
      with transaction(db()):
        issue, change = raise_request(record, actor, at=at)
        issue = issues_data.save(db(), issue, commit=False)
        requests_data.save(db(), change.object, commit=False)
        _append_all("request", record, change, commit=False)
        raised = Event("issue.raised_from_request", user.id, at, {"issue_id": issue.id})
        events_data.append(db(), "request", record.id, raised, commit=False)
        created = Event("issue.created", user.id, at, {})
        events_data.append(db(), "issue", issue.id, created, commit=False)
        _notify_event("issue", issue, created, commit=False)
      flash(f"Raised into Issue #{issue.id}.")
      return redirect(url_for("records.issue_detail", issue_id=issue.id))
    change = transition_request(
      record, target, actor, at=at, reason=request.form.get("reason") or None
    )
    requests_data.save(db(), change.object)
    _append_all("request", record, change)
  except CoreError as error:
    flash(str(error))
  return redirect(url_for("records.request_detail", request_id=request_id))


@bp.post("/requests/<int:request_id>/comment")
def request_comment(request_id: int) -> Response:
  """Add a comment event to a request."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  text = request.form.get("text", "").strip()
  if text and _can(actor, "request.comment", record):
    event = Event("request.comment", user.id, now(), {"text": text})
    events_data.append(db(), "request", record.id, event)
    _notify_event("request", record, event)
  elif text:
    flash("You cannot comment on this request.")
  return redirect(url_for("records.request_detail", request_id=request_id))


@bp.get("/requests/<int:request_id>/edit")
def request_edit(request_id: int) -> str | Response:
  """Show the edit form for a request."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  return render_template(
    "request_form.html", record=record, priorities=[p.value for p in Priority]
  )


@bp.post("/requests/<int:request_id>/edit")
def request_edit_save(request_id: int) -> str | Response:
  """Save request edits, asking first when a pending edit reopens it."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  priority = request.form.get("priority_suggestion", "")
  submitted = {
    "title": request.form.get("title", "").strip(),
    "description": request.form.get("description", "").strip(),
    "visibility": Visibility(request.form.get("visibility", "PRIVATE")),
    "domains": tuple(
      part.strip()
      for part in request.form.get("domains", "").split(",")
      if part.strip()
    ),
    "priority_suggestion": Priority(priority) if priority else None,
    "priority_unsure": "priority_unsure" in request.form,
  }
  fields = {
    name: value for name, value in submitted.items() if value != getattr(record, name)
  }
  try:
    change = edit_request(
      record,
      actor,
      at=now(),
      confirmed="confirmed" in request.form,
      **fields,
    )
  except ConfirmationRequired:
    return render_template("confirm_edit.html", record=record, fields=request.form)
  except CoreError as error:
    flash(str(error))
    return redirect(url_for("records.request_detail", request_id=request_id))
  requests_data.save(db(), change.object)
  _append_all("request", record, change)
  return redirect(url_for("records.request_detail", request_id=request_id))


@bp.get("/issues")
def issue_board() -> str | Response:
  """Show the issue board in status columns."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  all_issues = _viewable_issues(actor, issues_data.list_issues(db()))
  board = {
    status: [i for i in all_issues if i.status is status] for status in IssueStatus
  }
  return render_template("issue_board.html", board=board, names=_names())


@bp.get("/issues/<int:issue_id>")
def issue_detail(issue_id: int) -> str | Response:
  """Show one issue with facts, activity, comments, and actions."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  events = events_data.list_for(db(), "issue", issue_id)
  return render_template(
    "issue_detail.html",
    record=record,
    actions=_issue_actions(actor, record),
    can_edit=actor.is_admin or _can(actor, "issue.edit", record),
    can_change_priority=(
      actor.is_admin
      or actor.id == record.assignee_id
      or actor.id == record.requester_id
      or _can(actor, "issue.edit", record)
    ),
    priorities=[priority.value for priority in Priority],
    can_comment=_can_comment_issue(actor, record),
    events=events,
    comments=[e for e in events if e.event_type == "issue.comment"],
    share_links=sharing_data.list_for_object(db(), "issue", record.id),
    can_share=can_share(user, record),
    object_type="issue",
    issued_token=_issued_token("issue", record.id),
    names=_names(),
  )


@bp.post("/issues/<int:issue_id>/transition")
def issue_transition(issue_id: int) -> Response:
  """Run one issue state move through the core."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  target = IssueStatus(request.form["target"])
  try:
    change = transition_issue(record, target, actor, at=now())
    issues_data.save(db(), change.object)
    _append_all("issue", record, change)
  except CoreError as error:
    flash(str(error))
  return redirect(url_for("records.issue_detail", issue_id=issue_id))


@bp.post("/issues/<int:issue_id>/priority")
def issue_priority(issue_id: int) -> Response:
  """Change only an issue priority through the core."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  try:
    change = edit_issue(
      record,
      actor,
      at=now(),
      priority=Priority(request.form.get("priority", "HIGH")),
    )
    issues_data.save(db(), change.object)
    _append_all("issue", record, change)
  except CoreError as error:
    flash(str(error))
  return redirect(url_for("records.issue_detail", issue_id=issue_id))


@bp.post("/issues/<int:issue_id>/comment")
def issue_comment(issue_id: int) -> Response:
  """Add a comment event to an issue."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  text = request.form.get("text", "").strip()
  if text and _can_comment_issue(actor, record):
    event = Event("issue.comment", user.id, now(), {"text": text})
    events_data.append(db(), "issue", record.id, event)
    _notify_event("issue", record, event)
  elif text:
    flash("You cannot comment on this issue.")
  return redirect(url_for("records.issue_detail", issue_id=issue_id))


@bp.get("/issues/<int:issue_id>/edit")
def issue_edit(issue_id: int) -> str | Response:
  """Show the edit form for an issue."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  return render_template(
    "issue_form.html",
    record=record,
    priorities=[p.value for p in Priority],
    users=list_users(db()),
  )


@bp.post("/issues/<int:issue_id>/edit")
def issue_edit_save(issue_id: int) -> Response:
  """Save issue edits through the core."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  assignee = request.form.get("assignee_id", "")
  submitted = {
    "title": request.form.get("title", "").strip(),
    "description": request.form.get("description", "").strip(),
    "visibility": Visibility(request.form.get("visibility", "PRIVATE")),
    "domains": tuple(
      part.strip()
      for part in request.form.get("domains", "").split(",")
      if part.strip()
    ),
    "priority": Priority(request.form.get("priority", "HIGH")),
    "assignee_id": int(assignee) if assignee else None,
  }
  fields = {
    name: value for name, value in submitted.items() if value != getattr(record, name)
  }
  try:
    change = edit_issue(record, actor, at=now(), **fields)
  except CoreError as error:
    flash(str(error))
    return redirect(url_for("records.issue_detail", issue_id=issue_id))
  issues_data.save(db(), change.object)
  _append_all("issue", record, change)
  return redirect(url_for("records.issue_detail", issue_id=issue_id))


def is_staff(user) -> bool:
  """True when the user holds a staff role (admin or assignee)."""
  roles = list_roles(db(), user.id)
  return Role.ADMIN in roles or Role.ASSIGNEE in roles
