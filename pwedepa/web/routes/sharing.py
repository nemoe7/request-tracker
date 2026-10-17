"""Share-link creation, revocation, and link opening."""

from datetime import timedelta

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

from pwedepa.auth import actor_for_user, record_audit
from pwedepa.core import Event
from pwedepa.data import events as events_data
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import requests as requests_data
from pwedepa.data import sharing as sharing_data

from .. import now
from ._helpers import can_share, current_user, db, expiry_days, record_path

bp = Blueprint("sharing", __name__)


def _record(object_type: str, object_id: int):
  if object_type == "request":
    return requests_data.get(db(), object_id)
  if object_type == "issue":
    return issues_data.get(db(), object_id)
  abort(404)


def _detail_url(record, object_type: str) -> str:
  if record is None:
    return url_for("records.requests")
  return record_path(record, object_type)


def _notify_share(record, object_type: str, actor_id: int, message: str) -> None:
  if record.requester_id is None or record.requester_id == actor_id:
    return
  notifications_data.notify(
    db(),
    record.requester_id,
    "sharing",
    message,
    at=now(),
    object_type=object_type,
    object_id=record.id,
    actor_id=actor_id,
  )


@bp.post("/records/<object_type>/<int:object_id>/share")
def create(object_type: str, object_id: int) -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  record = _record(object_type, object_id)
  if record is None or not can_share(user, record):
    abort(404)
  days = expiry_days()
  expires_at = now() + timedelta(days=days) if days else None
  issued = sharing_data.create(
    db(),
    object_type,
    object_id,
    (request.form.get("permission", "VIEW"),),
    user.id,
    at=now(),
    expires_at=expires_at,
  )
  session["issued_share"] = {
    "object_type": object_type,
    "object_id": object_id,
    "token": issued.token,
  }
  event = Event(
    f"{object_type}.share_created", user.id, now(), {"link_id": issued.link.id}
  )
  events_data.append(db(), object_type, object_id, event)
  _notify_share(
    record, object_type, user.id, f"A share link was created for {record.title}"
  )
  record_audit(
    db(),
    "share_link.created",
    at=now(),
    actor_id=user.id,
    object_type=object_type,
    object_id=object_id,
    data={"link_id": issued.link.id, "permissions": list(issued.link.permissions)},
  )
  flash("Share link created. Copy it now. The app shows the plain link once.")
  return redirect(_detail_url(record, object_type))


@bp.post("/share-links/<int:link_id>/revoke")
def revoke(link_id: int) -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  link = sharing_data.get(db(), link_id)
  if link is None:
    abort(404)
  record = _record(link.object_type, link.object_id)
  is_admin = actor_for_user(db(), user.id).is_admin
  if not (is_admin or user.id == link.created_by_id or can_share(user, record)):
    abort(404)
  sharing_data.revoke(db(), link_id, at=now())
  if record is not None:
    event = Event(
      f"{link.object_type}.share_revoked", user.id, now(), {"link_id": link_id}
    )
    events_data.append(db(), link.object_type, link.object_id, event)
    _notify_share(
      record,
      link.object_type,
      user.id,
      f"A share link was revoked for {record.title}",
    )
  record_audit(
    db(),
    "share_link.revoked",
    at=now(),
    actor_id=user.id,
    object_type=link.object_type,
    object_id=link.object_id,
    data={"link_id": link_id},
  )
  flash("Share link revoked.")
  return redirect(_detail_url(record, link.object_type))


@bp.get("/share/<token>")
def open_link(token: str) -> str | Response:
  """Open a share link, or show the one-view notice when signed out."""
  link = sharing_data.find_by_token(db(), token)
  if link is None or not sharing_data.is_active(link, now()):
    return render_template("share_gone.jinja"), 404
  record = _record(link.object_type, link.object_id)
  if record is None:
    return render_template("share_gone.jinja"), 404
  if current_user() is not None:
    session["share_link_id"] = link.id
    record_audit(
      db(),
      "share_link.opened",
      at=now(),
      actor_id=current_user().id,
      object_type=link.object_type,
      object_id=link.object_id,
      data={"link_id": link.id},
    )
    return redirect(_detail_url(record, link.object_type))
  if link.view_consumed_at is not None:
    return render_template("share_gone.jinja"), 410
  return render_template("share_notice.jinja", link=link, record=record, token=token)


@bp.post("/share/<token>/view")
def consume_view(token: str) -> Response:
  """Spend the one signed-out view and open the item."""
  link = sharing_data.find_by_token(db(), token)
  if link is None or not sharing_data.is_active(link, now()):
    return render_template("share_gone.jinja"), 404
  record = _record(link.object_type, link.object_id)
  if current_user() is not None:
    session["share_link_id"] = link.id
    return redirect(_detail_url(record, link.object_type))
  if not sharing_data.consume_view(db(), link.id, at=now()):
    return render_template("share_gone.jinja"), 410
  session["anonymous_share_link_id"] = link.id
  record_audit(
    db(),
    "share_link.view_consumed",
    at=now(),
    object_type=link.object_type,
    object_id=link.object_id,
    data={"link_id": link.id},
  )
  return redirect(url_for("sharing.shared_record", link_id=link.id))


@bp.get("/shared/<int:link_id>")
def shared_record(link_id: int) -> str | Response:
  if session.get("anonymous_share_link_id") != link_id:
    return render_template("share_gone.jinja"), 404
  link = sharing_data.get(db(), link_id)
  if link is None or not sharing_data.is_active(link, now()):
    return render_template("share_gone.jinja"), 404
  record = _record(link.object_type, link.object_id)
  if record is None:
    return render_template("share_gone.jinja"), 404
  events = events_data.list_for(db(), link.object_type, link.object_id)
  html = render_template(
    "shared_record.jinja",
    link=link,
    record=record,
    object_type=link.object_type,
    comments=[
      event for event in events if event.event_type == f"{link.object_type}.comment"
    ],
  )
  session.pop("anonymous_share_link_id", None)
  return html
