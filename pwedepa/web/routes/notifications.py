"""The retained notification inbox."""

from flask import Blueprint, redirect, render_template, url_for
from werkzeug.wrappers import Response

from pwedepa.auth import get_user
from pwedepa.data import announcements as announcements_data
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import requests as requests_data

from ._helpers import current_user, db, record_path

bp = Blueprint("notifications", __name__)


@bp.get("/notifications")
def inbox() -> str | Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  notices = notifications_data.list_for_user(db(), user.id)
  names = {}
  links = {}
  for notice in notices:
    if notice.actor_id is not None and notice.actor_id not in names:
      actor = get_user(db(), notice.actor_id)
      names[notice.actor_id] = actor.display_name if actor else "Someone"
    if notice.object_type == "request":
      record = requests_data.get(db(), notice.object_id)
      links[notice.id] = record_path(record) if record else ""
    elif notice.object_type == "issue":
      record = issues_data.get(db(), notice.object_id)
      links[notice.id] = record_path(record, "issue") if record else ""
    elif notice.object_type == "announcement":
      found = announcements_data.get(db(), notice.object_id)
      links[notice.id] = f"/{found.slug}" if found else ""
  return render_template(
    "notifications.jinja", notices=notices, names=names, links=links
  )


@bp.post("/notifications/<int:notice_id>/dismiss")
def dismiss(notice_id: int) -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  notifications_data.delete_for_user(db(), user.id, notice_id)
  return redirect(url_for("notifications.inbox"))


@bp.post("/notifications/clear")
def clear() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  notifications_data.delete_all_for_user(db(), user.id)
  return redirect(url_for("notifications.inbox"))
