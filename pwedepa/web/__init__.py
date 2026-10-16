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
  app.config.update(
    DATABASE=os.environ.get("PWEDEPA_DB", "pwedepa.db"),
    WEBAUTHN_RP_ID=os.environ.get("PWEDEPA_RP_ID", "localhost"),
    WEBAUTHN_RP_NAME=os.environ.get("PWEDEPA_RP_NAME", "PwedePa"),
    WEBAUTHN_ORIGIN=os.environ.get("PWEDEPA_ORIGIN", "http://localhost:5000"),
    SESSION_COOKIE_SECURE=os.environ.get("PWEDEPA_COOKIE_SECURE", "1") == "1",
  )
  if config:
    app.config.update(config)

  data_db.connect(app.config["DATABASE"]).close()
  app.extensions["webauthn"] = WebAuthnConfig(
    rp_id=app.config["WEBAUTHN_RP_ID"],
    rp_name=app.config["WEBAUTHN_RP_NAME"],
    origin=app.config["WEBAUTHN_ORIGIN"],
  )

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
