"""Admin pages for users, audit, sharing, and site settings."""

from datetime import timedelta

from flask import (
  Blueprint,
  abort,
  current_app,
  flash,
  g,
  redirect,
  render_template,
  request,
  session,
  url_for,
)
from werkzeug.wrappers import Response

from pwedepa.auth import (
  AuthError,
  Role,
  actor_for_user,
  archive_user,
  assign_role,
  create_user,
  grant_permission,
  issue_enrollment_token,
  list_audit_events,
  list_direct_grants,
  list_passkeys,
  list_roles,
  list_users,
  reactivate_user,
  record_audit,
  revoke_passkey,
  revoke_permission,
  revoke_role,
)
from pwedepa.core import Effect, Event, Grant, Issue, Priority, Visibility
from pwedepa.data import domains as domains_data
from pwedepa.data import events as events_data
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import sharing as sharing_data
from pwedepa.data import site as site_data
from pwedepa.data.db import transaction

from .. import now
from ._helpers import choice, current_user, db, expiry_days, record_path

bp = Blueprint("admin", __name__)


@bp.before_request
def _require_admin() -> Response | None:
  """Keep every admin route behind one guard."""
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  if not actor_for_user(db(), user.id).is_admin:
    abort(403)
  g.admin_user = user
  return None


def _names() -> dict[int, str]:
  return {
    person.id: person.display_name for person in list_users(db(), include_archived=True)
  }


@bp.get("/admin")
def overview() -> str | Response:
  """Show admin sections and site controls."""
  return render_template(
    "admin.html",
    users=list_users(db(), include_archived=True),
    share_links=sharing_data.list_all(db()),
    site_messages=site_data.list_messages(db()),
    priorities=[priority.value for priority in Priority],
    domains=domains_data.load(current_app.config["DATABASE"]),
  )


@bp.get("/admin/config")
def domain_config() -> str | Response:
  """Show the Domain config in force, and the import control."""
  db_path = current_app.config["DATABASE"]
  mounted = domains_data.mounted_path()
  return render_template(
    "admin_config.html",
    domains=domains_data.load(db_path),
    active=domains_data.active_path(db_path),
    mounted=mounted,
    mounted_exists=bool(mounted and mounted.is_file()),
    imported=domains_data.imported_path(db_path),
    imported_exists=domains_data.imported_path(db_path).is_file(),
  )


@bp.post("/admin/config/import")
def domain_config_import() -> Response:
  """Import the mounted YAML, or the file the operator picked."""
  db_path = current_app.config["DATABASE"]
  uploaded = request.files.get("config")
  if uploaded is not None and uploaded.filename:
    raw = uploaded.read()
    source = uploaded.filename
  else:
    mounted = domains_data.mounted_path()
    if mounted is None or not mounted.is_file():
      flash("No config file is mounted. Choose a file to import.")
      return redirect(url_for("admin.domain_config"))
    raw = mounted.read_bytes()
    source = str(mounted)
  try:
    found = domains_data.import_bytes(raw, db_path)
  except domains_data.DomainConfigError as error:
    flash(f"The config file did not import: {error}")
    return redirect(url_for("admin.domain_config"))
  record_audit(
    db(),
    "domain_config.imported",
    at=now(),
    actor_id=g.admin_user.id,
    object_type="domain_config",
    object_id=None,
    data={"source": source, "domains": len(found)},
  )
  flash(f"Imported {len(found)} domains from {source}.")
  return redirect(url_for("admin.domain_config"))


@bp.get("/admin/users")
def users() -> str | Response:
  """List users with roles, grants, passkeys, and lifecycle actions."""
  people = list_users(db(), include_archived=True)
  details = {
    person.id: {
      "roles": list_roles(db(), person.id),
      "grants": list_direct_grants(db(), person.id),
      "passkeys": list_passkeys(db(), person.id, include_revoked=True),
    }
    for person in people
  }
  issued = session.pop("issued_enrollment", None)
  return render_template(
    "admin_users.html",
    people=people,
    details=details,
    roles=[role.value for role in Role],
    issued_token=issued.get("token") if issued else None,
  )


@bp.post("/admin/users")
def create_person() -> Response:
  """Create a user from the admin page."""
  try:
    person = create_user(
      db(),
      request.form.get("username", ""),
      request.form.get("display_name", ""),
      at=now(),
      actor_id=g.admin_user.id,
    )
    role = request.form.get("role", "")
    if role:
      assign_role(db(), person.id, Role(role), at=now(), actor_id=g.admin_user.id)
    flash(f"User {person.username} created.")
  except (AuthError, ValueError) as error:
    flash(str(error))
  return redirect(url_for("admin.users"))


@bp.post("/admin/users/<int:user_id>/archive")
def archive(user_id: int) -> Response:
  """Archive one user."""
  archive_user(db(), user_id, at=now(), actor_id=g.admin_user.id)
  flash("User archived.")
  return redirect(url_for("admin.users"))


@bp.post("/admin/users/<int:user_id>/reactivate")
def reactivate(user_id: int) -> Response:
  """Reactivate one user."""
  reactivate_user(db(), user_id, at=now(), actor_id=g.admin_user.id)
  flash("User reactivated.")
  return redirect(url_for("admin.users"))


@bp.post("/admin/users/<int:user_id>/roles")
def change_role(user_id: int) -> Response:
  """Assign or revoke one role."""
  role = Role(request.form["role"])
  if request.form.get("action") == "revoke":
    revoke_role(db(), user_id, role, at=now(), actor_id=g.admin_user.id)
  else:
    assign_role(db(), user_id, role, at=now(), actor_id=g.admin_user.id)
  return redirect(url_for("admin.users"))


@bp.post("/admin/users/<int:user_id>/grants")
def change_grant(user_id: int) -> Response:
  """Add or revoke one direct permission grant."""
  permission = request.form.get("permission", "").strip()
  effect = Effect(request.form.get("effect", "ALLOW"))
  if request.form.get("action") == "revoke":
    revoke_permission(
      db(), user_id, permission, effect, at=now(), actor_id=g.admin_user.id
    )
  elif permission:
    grant_permission(
      db(), user_id, Grant(permission, effect), at=now(), actor_id=g.admin_user.id
    )
  return redirect(url_for("admin.users"))


@bp.post("/admin/users/<int:user_id>/enrollment-token")
def enrollment_token(user_id: int) -> Response:
  """Issue an enrollment token and show it once."""
  try:
    issued = issue_enrollment_token(db(), user_id, at=now(), actor_id=g.admin_user.id)
    session["issued_enrollment"] = {"token": issued.token}
    flash("Enrollment token created. Copy it now.")
  except AuthError as error:
    flash(str(error))
  return redirect(url_for("admin.users"))


@bp.post("/admin/passkeys/<int:passkey_id>/revoke")
def passkey_revoke(passkey_id: int) -> Response:
  """Revoke any user's passkey."""
  try:
    revoke_passkey(db(), passkey_id, at=now(), actor_id=g.admin_user.id)
    flash("Passkey revoked.")
  except AuthError as error:
    flash(str(error))
  return redirect(url_for("admin.users"))


@bp.get("/admin/audit")
def audit() -> str | Response:
  """Show the latest audit events."""
  events = list_audit_events(db(), limit=200)
  return render_template("admin_audit.html", events=events, names=_names())


@bp.get("/admin/shares")
def shares() -> str | Response:
  """List every share link for admin review."""
  return render_template(
    "admin_shares.html", share_links=sharing_data.list_all(db()), names=_names()
  )


@bp.post("/admin/site-message")
def site_message() -> Response:
  """Save the one landing-page message."""
  days = expiry_days()
  site_data.save_message(
    db(),
    request.form.get("message", "").strip(),
    at=now(),
    created_by_id=g.admin_user.id,
    enabled="enabled" in request.form,
    expires_at=now() + timedelta(days=days) if days else None,
  )
  record_audit(
    db(),
    "site_message.saved",
    at=now(),
    actor_id=g.admin_user.id,
    object_type="site",
    object_id=None,
  )
  flash("Landing message saved.")
  return redirect(url_for("admin.overview"))


@bp.post("/admin/issues")
def create_issue() -> Response:
  """Create an Issue directly as an admin."""
  title = request.form.get("title", "").strip()
  if not title:
    flash("An issue needs a title.")
    return redirect(url_for("admin.overview"))
  at = now()
  assignee = request.form.get("assignee_id", type=int)
  record = Issue(
    id=0,
    title=title,
    description=request.form.get("description", "").strip(),
    requester_id=request.form.get("requester_id", type=int),
    assignee_id=assignee,
    priority=choice(Priority, request.form.get("priority", "HIGH"), Priority.HIGH),
    visibility=choice(
      Visibility, request.form.get("visibility", "PRIVATE"), Visibility.PRIVATE
    ),
    domains=tuple(
      name
      for name in request.form.getlist("domains")
      if name
      in {domain.name for domain in domains_data.load(current_app.config["DATABASE"])}
    ),
    created_at=at,
    updated_at=at,
  )
  with transaction(db()):
    record = issues_data.save(db(), record, commit=False)
    event = Event("issue.created", g.admin_user.id, at, {})
    events_data.append(db(), "issue", record.id, event, commit=False)
    for recipient in {record.requester_id, record.assignee_id}:
      if recipient is not None and recipient != g.admin_user.id:
        notifications_data.notify(
          db(),
          recipient,
          "activity",
          f"New record: {record.title}",
          at=at,
          object_type="issue",
          object_id=record.id,
          actor_id=g.admin_user.id,
          commit=False,
        )
  record_audit(
    db(),
    "issue.created_directly",
    at=at,
    actor_id=g.admin_user.id,
    object_type="issue",
    object_id=record.id,
  )
  return redirect(record_path(record, "issue"))
