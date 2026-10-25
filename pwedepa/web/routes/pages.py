from flask import (
  Blueprint,
  abort,
  current_app,
  redirect,
  render_template,
  request,
  send_from_directory,
  session,
  url_for,
)
from werkzeug.wrappers import Response

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


@bp.get("/workspace")
def old_workspace() -> Response:
  """The workspace lives at the base URL. Old links follow it."""
  return redirect(url_for("records.workspace", **request.args), code=302)


@bp.get("/home")
def home() -> Response:
  """Account pages moved to Settings, while `/` serves workspace views."""
  return redirect(url_for("records.workspace"))


@bp.get("/login")
def login() -> str | Response:
  if current_user() is not None:
    return redirect(url_for("records.workspace"))
  return render_template("login.jinja", site_message=site_data.get_active(db(), now()))


@bp.get("/enroll")
def enroll() -> str | Response:
  if current_user() is not None:
    return redirect(url_for("records.workspace"))
  return render_template("enroll.jinja")


@bp.get("/view-as/<mode>")
def view_as(mode: str) -> Response:
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
  """Serve `sw.js` from `/` so worker scope covers every route."""
  if current_app.config.get("DEMO_MODE"):
    response = Response(RETIRING_WORKER, mimetype="text/javascript")
  else:
    response = send_from_directory("static", "sw.js")
  response.headers["Service-Worker-Allowed"] = "/"
  return response
