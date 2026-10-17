"""Flask web shell: landing, passkey auth pages, and the signed-in home."""

import os
from datetime import UTC, datetime
from urllib.parse import urlparse

from flask import Flask, abort, g, request

from pwedepa.auth import WebAuthnConfig
from pwedepa.data import db as data_db

SESSION_COOKIE = "pwedepa_session"


def check_secret(secret_key: str, origin: str) -> None:
  """Refuse the sample secret on a public host. Every real run calls this."""
  host = urlparse(origin).hostname
  if secret_key == DEVELOPMENT_SECRET and host not in LOCAL_HOSTS:
    raise RuntimeError(f"{host or origin} needs its own PWEDEPA_SECRET_KEY")


DEVELOPMENT_SECRET = "pwedepa-dev-secret"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def create_app(config: dict | None = None) -> Flask:
  """Build the app from environment defaults plus explicit overrides."""
  app = Flask(__name__)
  app.secret_key = os.environ.get("PWEDEPA_SECRET_KEY", DEVELOPMENT_SECRET)
  # The public origin names the passkey, so the ID follows it unless the deploy
  # asks for a different one.
  origin = os.environ.get("PWEDEPA_ORIGIN", "http://localhost:5000")
  rp_id = os.environ.get("PWEDEPA_RP_ID") or urlparse(origin).hostname or "localhost"
  app.config.update(
    DATABASE=os.environ.get("PWEDEPA_DB", "pwedepa.db"),
    WEBAUTHN_RP_ID=rp_id,
    WEBAUTHN_RP_NAME=os.environ.get("PWEDEPA_RP_NAME", "PwedePa"),
    WEBAUTHN_ORIGIN=origin,
    SESSION_COOKIE_SECURE=os.environ.get("PWEDEPA_COOKIE_SECURE", "1") == "1",
    # Lax stops a form on another site from riding on the session cookie.
    SESSION_COOKIE_SAMESITE="Lax",
    DEMO_MODE=False,  # the frozen build asks for demo mode in code
    DEMO_SWITCH=False,  # the frozen build holds both page sets, so it shows the switch
  )
  if config:
    app.config.update(config)

  from .routes._helpers import domain_path, record_path

  app.jinja_env.globals["record_path"] = record_path
  app.jinja_env.globals["domain_path"] = domain_path

  if app.config.get("DEMO_MODE"):

    @app.after_request
    def preview_no_store(response):
      # Previews change often. Forbid storage so no page can go stale. Assets
      # keep the revalidating headers the static route already sends, so a
      # page switch reads them from the browser cache instead of refetching.
      if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
      return response

  data_db.connect(app.config["DATABASE"]).close()
  app.extensions["webauthn"] = WebAuthnConfig(
    rp_id=app.config["WEBAUTHN_RP_ID"],
    rp_name=app.config["WEBAUTHN_RP_NAME"],
    origin=app.config["WEBAUTHN_ORIGIN"],
  )

  @app.template_filter("stamp")
  def stamp(value: datetime | None, clock: str = "12") -> str:
    from .stamps import format_stamp

    return format_stamp(value, clock, now())

  @app.context_processor
  def inject_actor() -> dict:
    from pwedepa.data import notifications as notifications_data
    from pwedepa.data import preferences as preferences_data

    from .routes._helpers import client_view, current_user, db
    from .routes.records import is_staff

    user = current_user()
    count = 0
    clock = preferences_data.DEFAULT_CLOCK
    theme = preferences_data.DEFAULT_THEME
    if user is not None:
      clock = preferences_data.get_clock(db(), user.id)
      theme = preferences_data.get_theme(db(), user.id)
      if notifications_data.pip_visible(db(), user.id):
        count = notifications_data.count_for_user(db(), user.id)
    staff = user is not None and is_staff(user)
    viewing = staff and client_view()
    return {
      "user": user,
      "is_staff": staff and not viewing,
      "view_as_client": viewing,
      "can_view_as_client": staff,
      "notification_count": count,
      "clock": clock,
      "theme": theme,
      "demo_mode": bool(app.config.get("DEMO_MODE")),
      "demo_switch": bool(app.config.get("DEMO_SWITCH")),
    }

  @app.before_request
  def refuse_writes_in_client_view() -> None:
    """Records take no writes in the client view. Account settings stay open."""
    from .routes._helpers import client_view

    if not client_view() or request.method in ("GET", "HEAD", "OPTIONS"):
      return
    # Sign-out and the settings page are not record writes.
    endpoint = request.endpoint or ""
    if endpoint == "auth.logout" or endpoint.startswith("settings."):
      return
    if endpoint in {
      "auth.register_options",
      "auth.register_finish",
      "auth.passkey_revoke",
    }:
      return
    from .routes._helpers import current_user
    from .routes.records import is_staff

    user = current_user()
    if user is not None and is_staff(user):
      abort(403)

  @app.errorhandler(403)
  @app.errorhandler(404)
  def styled_error(error):
    from flask import render_template

    return render_template("error.html", error=error), error.code

  @app.teardown_appcontext
  def close_db(error: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
      connection.close()

  register_blueprints(app)
  return app


def now() -> datetime:
  """Return the current UTC time for auth calls."""
  return datetime.now(UTC)


from .routes import register_blueprints

__all__ = ["SESSION_COOKIE", "create_app", "now"]
