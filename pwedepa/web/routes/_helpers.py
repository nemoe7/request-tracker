"""Shared request helpers for the web routes."""

import math

from flask import current_app, g, request, session, url_for
from sqlalchemy.engine import Connection

from pwedepa.auth import (
  Role,
  WebAuthnConfig,
  actor_for_user,
  get_user,
  list_roles,
  resolve_session,
)
from pwedepa.data import db as data_db
from pwedepa.data import domains as domains_data

from .. import SESSION_COOKIE, now


def db() -> Connection:
  """Return this request's database connection, opening it on first use."""
  if "db" not in g:
    g.db = data_db.connect(current_app.config["DATABASE"])
  return g.db


def webauthn_config() -> WebAuthnConfig:
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
    days = float(submitted)
  except ValueError:
    return None
  # A number too large to read is still a number, so it takes the far end.
  if not math.isfinite(days):
    return MAX_EXPIRY_DAYS
  return max(1, min(MAX_EXPIRY_DAYS, int(days)))


def choice(enum_type, raw: str | None, default=None):
  """Read a submitted value into an enum, or hand back the default."""
  try:
    return enum_type(raw)
  except ValueError:
    return default


def can_share(user, record) -> bool:
  """An admin, or the requester of the item."""
  if user is None or record is None:
    return False
  return actor_for_user(db(), user.id).is_admin or user.id == record.requester_id


def client_view() -> bool:
  """True while a staff user checks the app the way a client sees it."""
  return session.get("view_as") == "client"


def safe_next() -> str | None:
  """Read the return path a form carries, or None to keep the default page."""
  path = request.form.get("next", "").strip()
  if not path.startswith("/") or path.startswith("//") or "\\" in path:
    return None
  return path


def db_path():
  return current_app.config["DATABASE"]


def record_slug(record) -> str:
  return domains_data.slug_for(record.domains, domains_data.load(db_path()))


def record_path(record, kind: str = "request", slug: str | None = None) -> str:
  """The domain-first URL for one item, under slug when given."""
  return f"/{slug or record_slug(record)}/{kind}s/{record.id}"


def is_staff(user) -> bool:
  """True when the user holds a staff role (admin or assignee)."""
  roles = list_roles(db(), user.id)
  return Role.ADMIN in roles or Role.ASSIGNEE in roles


def request_open_path(record, slug: str | None = None) -> str:
  """Open a request in the workspace for staff, or on its own page."""
  user = current_user()
  if user is not None and not client_view() and is_staff(user):
    return url_for("records.workspace", selected=record.id)
  return record_path(record, slug=slug)


def domain_path(name: str) -> str:
  """Return the Domain page path for one configured name, or an empty string."""
  found = domains_data.find(domains_data.slugify(name), db_path())
  return f"/{found.slug}" if found else ""


def domain_matches(record, slug: str) -> bool:
  found = domains_data.load(db_path())
  configured = {domain.slug for domain in found if domain.name in record.domains}
  return slug == domains_data.slug_for(record.domains, found) or slug in configured
