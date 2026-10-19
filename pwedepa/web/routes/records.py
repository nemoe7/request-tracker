"""Request and Issue pages. Every write routes through the core rules."""

from flask import (
  Blueprint,
  abort,
  current_app,
  flash,
  redirect,
  render_template,
  request,
  session,
  url_for,
)
from werkzeug.wrappers import Response

from pwedepa.auth import actor_for_user, list_users
from pwedepa.core import (
  Actor,
  ConfirmationRequired,
  CoreError,
  Event,
  Grant,
  Issue,
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
from pwedepa.data import announcements as announcements_data
from pwedepa.data import domains as domains_data
from pwedepa.data import events as events_data
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import requests as requests_data
from pwedepa.data import sharing as sharing_data
from pwedepa.data import subscriptions, workspace_reads
from pwedepa.data.db import transaction

from .. import now
from ._helpers import (
  can_share,
  choice,
  client_view,
  current_user,
  db,
  domain_matches,
  is_staff,
  record_path,
  safe_next,
)

bp = Blueprint("records", __name__)

REQUEST_LABELS = {
  RequestStatus.PENDING: "Move to pending",
  RequestStatus.DELAYED: "Delay",
  RequestStatus.RAISED: "Raise to issue",
  RequestStatus.REJECTED: "Reject",
  RequestStatus.FULFILLED: "Fulfill",
}
STATUS_WORDS = {
  RequestStatus.OPEN: "New, not yet reviewed",
  RequestStatus.PENDING: "Waiting for review",
  RequestStatus.DELAYED: "Delayed",
  RequestStatus.RAISED: "Turned into work",
  RequestStatus.REJECTED: "Not accepted",
  RequestStatus.FULFILLED: "Done",
}


def _user():
  user = current_user()
  if user is None:
    return None
  return user


def _actor(user):
  return actor_for_user(db(), user.id)


def _configured_domains():
  return domains_data.load(current_app.config["DATABASE"])


def _picked_domains() -> tuple[str, ...]:
  """Read the Domain checkboxes and keep the configured names."""
  names = {domain.name for domain in _configured_domains()}
  return tuple(name for name in request.form.getlist("domains") if name in names)


def _picked_domain() -> tuple[str, ...]:
  """Read the one Domain a request belongs to, and keep it if configured."""
  names = {domain.name for domain in _configured_domains()}
  chosen = str(request.form.get("domain", "")).strip()
  return (chosen,) if chosen in names else ()


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
  """Add the active share link grants for one item to an actor."""
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


@bp.get("/")
def workspace() -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not is_staff(user) or client_view():
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
    elif queue == "public":
      rows = [r for r in rows if r.visibility is Visibility.PUBLIC]
    row_kind = "request"

  selected = None
  picked = False
  selected_id = request.args.get("selected", type=int)
  if row_kind == "request" and selected_id:
    # A move can filter the row out. The open request keeps its pane either way.
    selected = next((r for r in all_requests if r.id == selected_id), None)
    picked = selected is not None
  if selected is not None:
    workspace_reads.mark(db(), user.id, "request", selected.id, at=now())
  read_ids = workspace_reads.read_ids(db(), user.id, row_kind)
  # Gmail keeps one list. Unread work still leads, and the row itself reads bold.
  rows = [row for row in rows if row.id not in read_ids] + [
    row for row in rows if row.id in read_ids
  ]
  if (
    selected is None
    and row_kind == "request"
    and rows
    and not current_app.config.get("DEMO_MODE")
  ):
    # A wide screen keeps the pane open, so a load with no choice fills it.
    # The default read stays unread until someone picks the row. The frozen
    # demo opens one record per page instead, so a static file holds no form.
    selected = rows[0]
  domains = sorted({d for r in all_requests + all_issues for d in r.domains})
  # Each value keeps its own quotes, so a domain with a comma stays one item.
  filters = [
    f'{name} "{value}"'
    for name, value in (
      ("domain", domain),
      ("visibility", visibility),
      ("status", status_filter),
    )
    if value
  ]
  return render_template(
    "workspace.jinja",
    queue=queue,
    domain=domain,
    visibility=visibility,
    status_filter=status_filter,
    filters=[word for word in filters if word],
    statuses=[status.value for status in RequestStatus]
    + [status.value for status in IssueStatus if status is not IssueStatus.OPEN],
    domains=domains,
    counts=counts,
    rows=rows,
    row_kind=row_kind,
    read_ids=read_ids,
    selected=selected,
    picked=picked,
    selected_actions=_request_actions(actor, selected) if selected else [],
    selected_events=(
      events_data.list_for(db(), "request", selected.id) if selected else []
    ),
    selected_can_edit=selected is not None and _can(actor, "request.edit", selected),
    selected_can_comment=(
      selected is not None and _can(actor, "request.comment", selected)
    ),
    selected_share_links=(
      sharing_data.list_for_object(db(), "request", selected.id) if selected else []
    ),
    selected_can_share=selected is not None and can_share(user, selected),
    selected_token=_issued_token("request", selected.id) if selected else None,
    return_to=request.full_path if request.query_string else request.path,
    names=_names(),
  )


@bp.get("/<slug>")
def domain_page(slug: str) -> str | Response:
  found = domains_data.find(slug, current_app.config["DATABASE"])
  if found is None:
    abort(404)
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  requests = [
    record
    for record in _viewable_requests(actor, requests_data.list_requests(db()))
    if found.name in record.domains
  ]
  issues = [
    record
    for record in _viewable_issues(actor, issues_data.list_issues(db()))
    if found.name in record.domains
  ]
  return render_template(
    "domain.jinja",
    domain=found,
    announcements=announcements_data.list_for_slug(db(), found.slug),
    subscribed=subscriptions.subscribed(db(), user.id, found.slug),
    requests=requests,
    issues=issues,
    status_words=STATUS_WORDS,
    names=_names(),
  )


@bp.get("/requests")
def requests() -> str | Response:
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
  visible = [*mine, *public]
  selected_id = request.args.get("selected", type=int)
  selected = (
    next((r for r in visible if r.id == selected_id), None) if selected_id else None
  )
  return render_template(
    "requests.jinja",
    mine=mine,
    public=public,
    visible=visible,
    replies=events_data.newest_comments(db(), "request", [r.id for r in visible]),
    selected=selected,
    status_words=STATUS_WORDS,
    names=_names(),
  )


@bp.get("/requests/new")
def request_new() -> str | Response:
  """A request lives in a Domain, so the create step starts by picking one."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not authorize(_actor(user), "request.create"):
    flash("Your account cannot create requests.")
    return redirect(url_for("records.requests"))
  domains = _configured_domains()
  if len(domains) == 1:
    return redirect(url_for("records.request_new_in_domain", slug=domains[0].slug))
  return render_template("domain_choice.jinja", domains=domains)


@bp.get("/<slug>/requests/new")
def request_new_in_domain(slug: str) -> str | Response:
  found = domains_data.find(slug, current_app.config["DATABASE"])
  if found is None:
    abort(404)
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not authorize(_actor(user), "request.create"):
    flash("Your account cannot create requests.")
    return redirect(url_for("records.domain_page", slug=slug))
  return render_template(
    "request_form.jinja",
    record=None,
    domain=found,
    priorities=[p.value for p in Priority],
    domains=_configured_domains(),
  )


def _create_request(user, domain_name: str) -> Response | None:
  """Create a request in one Domain, or return the redirect to send back."""
  actor = _actor(user)
  if not authorize(actor, "request.create"):
    flash("Your account cannot create requests.")
    return redirect(url_for("records.requests"))
  title = request.form.get("title", "").strip()
  if not title:
    flash("A request needs a title.")
    return None
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
        priority_suggestion=choice(Priority, priority, None),
        priority_unsure="priority_unsure" in request.form,
        visibility=choice(
          Visibility, request.form.get("visibility", "PRIVATE"), Visibility.PRIVATE
        ),
        domains=(domain_name,) if domain_name else (),
        created_at=at,
        updated_at=at,
      ),
      commit=False,
    )
    created = Event("request.created", user.id, at)
    events_data.append(db(), "request", record.id, created, commit=False)
    _notify_event("request", record, created, commit=False)
  return redirect(record_path(record))


@bp.post("/<slug>/requests")
def request_create_in_domain(slug: str) -> Response:
  found = domains_data.find(slug, current_app.config["DATABASE"])
  if found is None:
    abort(404)
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  done = _create_request(user, found.name)
  if done is not None:
    return done
  flash("A request needs a title.")
  return redirect(url_for("records.request_new_in_domain", slug=slug))


@bp.post("/requests")
def request_create() -> Response:
  """The old flat endpoint. It keeps the Domain when a form posts one."""
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  picked = _picked_domain()
  done = _create_request(user, picked[0] if picked else "")
  if done is not None:
    return done
  flash("A request needs a title.")
  return redirect(url_for("records.request_new"))


@bp.get("/<slug>/requests/<int:request_id>")
def request_detail(slug: str, request_id: int) -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  if not domain_matches(record, slug):
    abort(404)
  if is_staff(user):
    workspace_reads.mark(db(), user.id, "request", record.id, at=now())
  events = events_data.list_for(db(), "request", request_id)
  read_only = client_view()
  return render_template(
    "request_detail.jinja",
    record=record,
    actions=[] if read_only else _request_actions(actor, record),
    can_edit=_can(actor, "request.edit", record) and not read_only,
    can_comment=_can(actor, "request.comment", record) and not read_only,
    events=events,
    share_links=sharing_data.list_for_object(db(), "request", record.id),
    can_share=can_share(user, record) and not read_only,
    object_type="request",
    issued_token=_issued_token("request", record.id),
    names=_names(),
  )


@bp.post("/requests/<int:request_id>/transition")
def request_transition(request_id: int) -> Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  target = choice(RequestStatus, request.form.get("target", ""), None)
  if target is None:
    flash("This record cannot move to that status.")
    return redirect(record_path(record))
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
      return redirect(record_path(issue, "issue"))
    change = transition_request(
      record, target, actor, at=at, reason=request.form.get("reason") or None
    )
    requests_data.save(db(), change.object)
    _append_all("request", record, change)
  except CoreError as error:
    flash(str(error))
  return redirect(safe_next() or record_path(record))


@bp.post("/requests/<int:request_id>/comment")
def request_comment(request_id: int) -> Response:
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
  return redirect(safe_next() or record_path(record))


@bp.get("/requests/<int:request_id>/edit")
def request_edit(request_id: int) -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  return render_template(
    "request_form.jinja",
    record=record,
    priorities=[p.value for p in Priority],
    domains=_configured_domains(),
  )


@bp.post("/requests/<int:request_id>/edit")
def request_edit_save(request_id: int) -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_request(actor, request_id)
  priority = request.form.get("priority_suggestion", "")
  submitted = {
    "title": request.form.get("title", "").strip(),
    "description": request.form.get("description", "").strip(),
    "visibility": choice(
      Visibility, request.form.get("visibility", ""), record.visibility
    ),
    "domains": _picked_domain(),
    "priority_suggestion": (
      choice(Priority, priority, record.priority_suggestion) if priority else None
    ),
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
    fields = [
      (key, value) for key in request.form for value in request.form.getlist(key)
    ]
    return render_template("confirm_edit.jinja", record=record, fields=fields)
  except CoreError as error:
    flash(str(error))
    return redirect(record_path(record))
  requests_data.save(db(), change.object)
  _append_all("request", record, change)
  return redirect(record_path(record))


@bp.get("/issues")
def issue_board() -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  all_issues = _viewable_issues(actor, issues_data.list_issues(db()))
  board = {
    status: [i for i in all_issues if i.status is status] for status in IssueStatus
  }
  return render_template("issue_board.jinja", board=board, names=_names())


@bp.get("/<slug>/issues/<int:issue_id>")
def issue_detail(slug: str, issue_id: int) -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  if not domain_matches(record, slug):
    abort(404)
  if is_staff(user):
    workspace_reads.mark(db(), user.id, "issue", record.id, at=now())
  events = events_data.list_for(db(), "issue", issue_id)
  source_request = (
    requests_data.get(db(), record.source_request_id)
    if record.source_request_id
    else None
  )
  if source_request is not None and not _can(actor, "request.view", source_request):
    source_request = None
  read_only = client_view()
  return render_template(
    "issue_detail.jinja",
    record=record,
    actions=[] if read_only else _issue_actions(actor, record),
    can_edit=(actor.is_admin or _can(actor, "issue.edit", record)) and not read_only,
    can_change_priority=not read_only
    and (
      actor.is_admin
      or actor.id == record.assignee_id
      or actor.id == record.requester_id
      or _can(actor, "issue.edit", record)
    ),
    priorities=[priority.value for priority in Priority],
    can_comment=_can_comment_issue(actor, record) and not read_only,
    events=events,
    comments=[e for e in events if e.event_type == "issue.comment"],
    share_links=sharing_data.list_for_object(db(), "issue", record.id),
    can_share=can_share(user, record) and not read_only,
    object_type="issue",
    issued_token=_issued_token("issue", record.id),
    source_request=source_request,
    names=_names(),
  )


@bp.post("/issues/<int:issue_id>/transition")
def issue_transition(issue_id: int) -> Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  target = choice(IssueStatus, request.form.get("target", ""), None)
  if target is None:
    flash("This record cannot move to that status.")
    return redirect(record_path(record, "issue"))
  try:
    change = transition_issue(record, target, actor, at=now())
    issues_data.save(db(), change.object)
    _append_all("issue", record, change)
  except CoreError as error:
    flash(str(error))
  return redirect(record_path(record, "issue"))


@bp.post("/issues/<int:issue_id>/priority")
def issue_priority(issue_id: int) -> Response:
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
      priority=choice(Priority, request.form.get("priority", "HIGH"), Priority.HIGH),
    )
    issues_data.save(db(), change.object)
    _append_all("issue", record, change)
  except CoreError as error:
    flash(str(error))
  return redirect(record_path(record, "issue"))


@bp.post("/issues/<int:issue_id>/comment")
def issue_comment(issue_id: int) -> Response:
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
  return redirect(record_path(record, "issue"))


@bp.get("/<slug>/issues/new")
def issue_new_in_domain(slug: str) -> str | Response:
  found = domains_data.find(slug, current_app.config["DATABASE"])
  if found is None:
    abort(404)
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not is_staff(user):
    flash("Your account cannot create issues.")
    return redirect(url_for("records.domain_page", slug=slug))
  return render_template(
    "issue_form.jinja",
    record=None,
    domain=found,
    priorities=[p.value for p in Priority],
    users=list_users(db()),
    domains=_configured_domains(),
  )


@bp.post("/<slug>/issues")
def issue_create_in_domain(slug: str) -> Response:
  found = domains_data.find(slug, current_app.config["DATABASE"])
  if found is None:
    abort(404)
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  if not authorize(actor, "issue.create"):
    flash("Your account cannot create issues.")
    return redirect(url_for("records.domain_page", slug=slug))
  title = request.form.get("title", "").strip()
  if not title:
    flash("An issue needs a title.")
    return redirect(url_for("records.issue_new_in_domain", slug=slug))
  at = now()
  assignee = request.form.get("assignee_id", "")
  with transaction(db()):
    record = issues_data.save(
      db(),
      Issue(
        id=0,
        title=title,
        description=request.form.get("description", "").strip(),
        requester_id=user.id,
        assignee_id=int(assignee) if assignee else None,
        priority=choice(Priority, request.form.get("priority", "HIGH"), Priority.HIGH),
        visibility=choice(
          Visibility, request.form.get("visibility", "PRIVATE"), Visibility.PRIVATE
        ),
        domains=(found.name,),
        created_at=at,
        updated_at=at,
      ),
      commit=False,
    )
    created = Event("issue.created", user.id, at, {})
    events_data.append(db(), "issue", record.id, created, commit=False)
    _notify_event("issue", record, created, commit=False)
  return redirect(record_path(record, "issue"))


@bp.get("/issues/<int:issue_id>/edit")
def issue_edit(issue_id: int) -> str | Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  return render_template(
    "issue_form.jinja",
    record=record,
    priorities=[p.value for p in Priority],
    users=list_users(db()),
    domains=_configured_domains(),
  )


@bp.post("/issues/<int:issue_id>/edit")
def issue_edit_save(issue_id: int) -> Response:
  user = _user()
  if user is None:
    return redirect(url_for("pages.login"))
  actor = _actor(user)
  record, actor = _load_issue(actor, issue_id)
  assignee = request.form.get("assignee_id", "")
  submitted = {
    "title": request.form.get("title", "").strip(),
    "description": request.form.get("description", "").strip(),
    "visibility": choice(
      Visibility, request.form.get("visibility", ""), record.visibility
    ),
    "domains": _picked_domains(),
    "priority": choice(Priority, request.form.get("priority", ""), record.priority),
    "assignee_id": int(assignee) if assignee else None,
  }
  fields = {
    name: value for name, value in submitted.items() if value != getattr(record, name)
  }
  try:
    change = edit_issue(record, actor, at=now(), **fields)
  except CoreError as error:
    flash(str(error))
    return redirect(record_path(record, "issue"))
  issues_data.save(db(), change.object)
  _append_all("issue", record, change)
  return redirect(record_path(record, "issue"))
