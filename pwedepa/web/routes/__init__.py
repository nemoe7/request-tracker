"""Route blueprints for the web shell."""

from flask import Flask

from .auth import bp as auth_bp
from .pages import bp as pages_bp
from .records import bp as records_bp


def register_blueprints(app: Flask) -> None:
  """Attach every blueprint to the app."""
  app.register_blueprint(pages_bp)
  app.register_blueprint(auth_bp)
  app.register_blueprint(records_bp)
