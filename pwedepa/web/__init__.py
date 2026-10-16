"""Flask web shell: landing, passkey auth pages, and the signed-in home."""

import os
from datetime import UTC, datetime

from flask import Flask, g

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
    DEMO_MODE=os.environ.get("PWEDEPA_DEMO", "0") == "1",
  )
  if config:
    app.config.update(config)

  data_db.connect(app.config["DATABASE"]).close()
  app.extensions["webauthn"] = WebAuthnConfig(
    rp_id=app.config["WEBAUTHN_RP_ID"],
    rp_name=app.config["WEBAUTHN_RP_NAME"],
    origin=app.config["WEBAUTHN_ORIGIN"],
  )

  @app.context_processor
  def inject_actor() -> dict:
    from pwedepa.data import notifications as notifications_data

    from .routes._helpers import current_user, db
    from .routes.records import is_staff

    user = current_user()
    count = 0
    if user is not None and notifications_data.pip_visible(db(), user.id):
      count = notifications_data.count_for_user(db(), user.id)
    return {
      "user": user,
      "is_staff": user is not None and is_staff(user),
      "notification_count": count,
      "demo_mode": bool(app.config.get("DEMO_MODE")),
    }

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
