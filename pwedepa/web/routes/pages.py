"""HTML pages and the service worker route."""

from flask import (
  Blueprint,
  abort,
  current_app,
  redirect,
  render_template,
  send_from_directory,
  session,
  url_for,
)
from werkzeug.wrappers import Response

from pwedepa.auth import list_passkeys
from pwedepa.data import site as site_data

from .. import now
from ._helpers import current_user, db

bp = Blueprint("pages", __name__)

# Demo previews serve a retiring worker instead of the caching one. Any
# worker a preview browser installed deletes its caches and unregisters.
RETIRING_WORKER = """self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.claim()),
  );
});
"""


@bp.get("/health")
def health() -> Response:
  """Answer the container probe. The database must open for a plain ok."""
  db().exec_driver_sql("SELECT 1").fetchone()
  return Response("ok\n", mimetype="text/plain")


@bp.get("/")
def landing() -> str | Response:
  """Show the public landing page, or jump to the role home when signed in."""
  user = current_user()
  if user is not None:
    from .records import is_staff

    if is_staff(user):
      return redirect(url_for("records.workspace"))
    return redirect(url_for("records.requests"))
  return render_template("landing.html", site_message=site_data.get_active(db(), now()))


@bp.get("/login")
def login() -> str | Response:
  """Show the passkey sign-in page, or send a signed-in visitor to the home."""
  if current_user() is not None:
    return redirect(url_for("pages.home"))
  return render_template("login.html")


@bp.get("/enroll")
def enroll() -> str | Response:
  """Show the enrollment page, or send a signed-in visitor to the home."""
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


@bp.get("/view-as/<mode>")
def view_as(mode: str) -> Response:
  """Switch a staff user between the staff view and the read-only client view."""
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  from .records import is_staff

  if not is_staff(user) or mode not in {"client", "staff"}:
    abort(404)
  if mode == "client":
    session["view_as"] = "client"
    return redirect(url_for("records.requests"))
  session.pop("view_as", None)
  return redirect(url_for("records.workspace"))


@bp.get("/sw.js")
def service_worker() -> Response:
  """Serve the worker from the root so its scope covers the whole app."""
  if current_app.config.get("DEMO_MODE"):
    response = Response(RETIRING_WORKER, mimetype="text/javascript")
  else:
    response = send_from_directory("static", "sw.js")
  response.headers["Service-Worker-Allowed"] = "/"
  return response
