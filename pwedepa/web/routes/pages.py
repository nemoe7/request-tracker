"""HTML pages and the service worker route."""

from flask import (
  Blueprint,
  current_app,
  redirect,
  render_template,
  send_from_directory,
  url_for,
)
from werkzeug.wrappers import Response

from pwedepa.auth import list_passkeys
from pwedepa.data import site as site_data

from .. import now
from ._helpers import current_user, db

bp = Blueprint("pages", __name__)


@bp.get("/")
def landing() -> str | Response:
  """Show the public landing page, or jump to the role home when signed in."""
  user = current_user()
  if user is not None:
    from .records import is_staff

    if is_staff(user):
      return redirect(url_for("records.workspace"))
    return redirect(url_for("records.my_requests"))
  return render_template("landing.html", site_message=site_data.get_active(db(), now()))


@bp.get("/login")
def login() -> str | Response:
  """Show the passkey sign-in page, or enter the demo when demo mode is on."""
  if current_app.config.get("DEMO_MODE"):
    return redirect(url_for("demo.demo"))
  if current_user() is not None:
    return redirect(url_for("pages.home"))
  return render_template("login.html")


@bp.get("/enroll")
def enroll() -> str | Response:
  """Show the enrollment page, or enter the demo when demo mode is on."""
  if current_app.config.get("DEMO_MODE"):
    return redirect(url_for("demo.demo"))
  if current_user() is not None:
    return redirect(url_for("pages.home"))
  return render_template("enroll.html")


@bp.get("/home")
def home() -> str | Response:
  """Show the signed-in shell: account, passkeys, and section entries."""
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  passkeys = list_passkeys(db(), user.id)
  return render_template("home.html", user=user, passkeys=passkeys)


@bp.get("/sw.js")
def service_worker() -> Response:
  """Serve the worker from the root so its scope covers the whole app."""
  response = send_from_directory("static", "sw.js")
  response.headers["Service-Worker-Allowed"] = "/"
  return response
