"""Shared request helpers for the web routes."""

from flask import current_app, g, request
from sqlalchemy.engine import Connection

from pwedepa.auth import WebAuthnConfig, get_user, resolve_session
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
  """Return the signed-in user for the session cookie, or None."""
  token = request.cookies.get(SESSION_COOKIE)
  if not token:
    return None
  session = resolve_session(db(), token, at=now())
  if session is None:
    return None
  return get_user(db(), session.user_id)
