"""User settings, including notification preferences."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.wrappers import Response

from pwedepa.auth import (
  AuthError,
  Role,
  list_passkeys,
  list_roles,
  update_display_name,
  update_username,
)
from pwedepa.data import notifications as notifications_data
from pwedepa.data import preferences as preferences_data

from .. import now
from ._helpers import current_user, db

bp = Blueprint("settings", __name__)


@bp.get("/settings")
def settings() -> str | Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  return render_template(
    "settings.jinja",
    passkeys=list_passkeys(db(), user.id),
    preferences=notifications_data.preferences(db(), user.id),
    is_admin=Role.ADMIN in list_roles(db(), user.id),
  )


@bp.post("/settings/profile")
def profile() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  try:
    update_display_name(
      db(),
      user.id,
      request.form.get("display_name", ""),
      at=now(),
      actor_id=user.id,
    )
    flash("Display name saved.")
  except AuthError as error:
    flash(str(error))
  return redirect(url_for("settings.settings"))


@bp.post("/settings/username")
def username() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  try:
    update_username(
      db(),
      user.id,
      request.form.get("username", ""),
      at=now(),
      actor_id=user.id,
    )
    flash("Username saved.")
  except AuthError as error:
    flash(str(error))
  return redirect(url_for("settings.settings"))


@bp.post("/settings/clock")
def clock() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  picked = request.form.get("clock", "")
  if picked in preferences_data.CLOCKS:
    preferences_data.set_clock(db(), user.id, picked)
    flash("Time format saved.")
  else:
    flash("Unknown time format.")
  return redirect(url_for("settings.settings"))


@bp.post("/settings/font-size")
def font_size() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  try:
    picked = int(request.form.get("font_size", ""))
  except ValueError:
    picked = 0
  if picked not in preferences_data.FONT_SIZES:
    flash(
      "Pick a text size from "
      f"{preferences_data.MIN_FONT_SIZE} to {preferences_data.MAX_FONT_SIZE} percent."
    )
    return redirect(url_for("settings.settings"))
  preferences_data.set_font_size(db(), user.id, picked)
  if request.headers.get("X-Requested-With") == "fetch":
    return Response("", status=204)
  flash("Text size saved.")
  return redirect(url_for("settings.settings"))


@bp.post("/settings/theme")
def theme() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  picked = request.form.get("theme", "")
  if picked in preferences_data.THEMES:
    preferences_data.set_theme(db(), user.id, picked)
  return Response("", status=204)


@bp.post("/settings/notifications")
def notification_preferences() -> Response:
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  for category in notifications_data.CATEGORIES:
    notifications_data.set_preference(
      db(),
      user.id,
      category,
      enabled=f"{category}_enabled" in request.form,
      inbox_enabled=f"{category}_inbox" in request.form,
      pip_enabled=f"{category}_pip" in request.form,
    )
  if request.headers.get("X-Autosave"):
    return Response("", status=204)
  flash("Notification settings saved.")
  return redirect(url_for("settings.settings"))
