"""Route blueprints for the web shell."""

from flask import Flask

from .admin import bp as admin_bp
from .auth import bp as auth_bp
from .demo import bp as demo_bp
from .notifications import bp as notifications_bp
from .pages import bp as pages_bp
from .records import bp as records_bp
from .settings import bp as settings_bp
from .sharing import bp as sharing_bp


def register_blueprints(app: Flask) -> None:
  """Attach every blueprint to the app."""
  app.register_blueprint(pages_bp)
  app.register_blueprint(auth_bp)
  app.register_blueprint(records_bp)
  app.register_blueprint(sharing_bp)
  app.register_blueprint(notifications_bp)
  app.register_blueprint(settings_bp)
  app.register_blueprint(admin_bp)
  app.register_blueprint(demo_bp)
