"""Shared request helpers for the web routes."""

from flask import current_app, g, request
from sqlalchemy.engine import Connection

from pwedepa.auth import WebAuthnConfig, actor_for_user, get_user, resolve_session
from pwedepa.data import db as data_db

from .. import SESSION_COOKIE, now


def db() -> Connection:
  """Return this request's database connection, opening it on first use."""
  if "db" not in g:
    g.db = data_db.connect(current_app.config["DATABASE"])
  return g.db


def webauthn_config() -> WebAuthnConfig:
  """Return the app WebAuthn configuration."""
  return current_app.extensions["webauthn"]


def current_user():
  """Return the signed-in user, or the demo seat user in demo mode."""
  token = request.cookies.get(SESSION_COOKIE)
  if token:
    session = resolve_session(db(), token, at=now())
    if session is not None:
      return get_user(db(), session.user_id)
  if current_app.config.get("DEMO_MODE"):
    from .demo import seat_user

    return seat_user()
  return None


# 10 years. A link or a message may not outlive the person who made it.
MAX_EXPIRY_DAYS = 3650


def expiry_days() -> int | None:
  """Read the day count from the form, or None for no expiry. Clamp to 1-3650."""
  submitted = request.form.get("expires_days", "").strip()
  if not submitted:
    return None
  # A number field submits exponent forms such as "1e3", so read a float first.
  try:
    days = int(float(submitted))
  except (ValueError, OverflowError):
    return None
  return max(1, min(MAX_EXPIRY_DAYS, days))


def can_share(user, record) -> bool:
  """Return whether this user may share this record. An admin, or its requester."""
  if user is None or record is None:
    return False
  return actor_for_user(db(), user.id).is_admin or user.id == record.requester_id
