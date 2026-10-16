"""The retained notification inbox."""

from flask import Blueprint, redirect, render_template, url_for
from werkzeug.wrappers import Response

from pwedepa.auth import get_user
from pwedepa.data import notifications as notifications_data

from ._helpers import current_user, db

bp = Blueprint("notifications", __name__)


@bp.get("/notifications")
def inbox() -> str | Response:
  """Show the signed-in user's retained notices."""
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  notices = notifications_data.list_for_user(db(), user.id)
  names = {}
  for notice in notices:
    if notice.actor_id is not None and notice.actor_id not in names:
      actor = get_user(db(), notice.actor_id)
      names[notice.actor_id] = actor.display_name if actor else "Someone"
  return render_template("notifications.html", notices=notices, names=names)
