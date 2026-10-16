"""Flask web shell: landing, passkey auth pages, and the signed-in home."""

import os
from datetime import UTC, datetime

from flask import Flask, g, request

from pwedepa.auth import WebAuthnConfig
from pwedepa.data import db as data_db

SESSION_COOKIE = "pwedepa_session"


def create_app(config: dict | None = None) -> Flask:
  """Build the app from environment defaults plus explicit overrides."""
  app = Flask(__name__)
  app.secret_key = os.environ.get("PWEDEPA_SECRET_KEY", "pwedepa-dev-secret")
  app.config.update(
    DATABASE=os.environ.get("PWEDEPA_DB", "pwedepa.db"),
    WEBAUTHN_RP_ID=os.environ.get("PWEDEPA_RP_ID", "localhost"),
    WEBAUTHN_RP_NAME=os.environ.get("PWEDEPA_RP_NAME", "PwedePa"),
    WEBAUTHN_ORIGIN=os.environ.get("PWEDEPA_ORIGIN", "http://localhost:5000"),
    SESSION_COOKIE_SECURE=os.environ.get("PWEDEPA_COOKIE_SECURE", "1") == "1",
    DEMO_MODE=False,  # the frozen build asks for demo mode in code
    DEMO_SWITCH=False,  # the frozen build holds both page sets, so it shows the switch
  )
  if config:
    app.config.update(config)

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

    from .routes._helpers import current_user, db
    from .routes.records import is_staff

    user = current_user()
    count = 0
    clock = preferences_data.DEFAULT_CLOCK
    if user is not None:
      clock = preferences_data.get_clock(db(), user.id)
      if notifications_data.pip_visible(db(), user.id):
        count = notifications_data.count_for_user(db(), user.id)
    return {
      "user": user,
      "is_staff": user is not None and is_staff(user),
      "notification_count": count,
      "clock": clock,
      "demo_mode": bool(app.config.get("DEMO_MODE")),
      "demo_switch": bool(app.config.get("DEMO_SWITCH")),
    }

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
