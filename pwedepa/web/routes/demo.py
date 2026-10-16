"""Opt-in demo entry. It stays off unless PWEDEPA_DEMO=1."""

from flask import Blueprint, abort, current_app, redirect, url_for
from werkzeug.wrappers import Response

from pwedepa.auth import (
  Role,
  assign_role,
  create_session,
  create_user,
  get_user_by_username,
)
from pwedepa.auth.sessions import SESSION_TTL
from pwedepa.core import Issue, Priority, Request, Visibility
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data

from .. import SESSION_COOKIE, now
from ._helpers import db

bp = Blueprint("demo", __name__)

# The demo seat lives server-side. Preview frames can block the session
# cookie, and the demo must still open with one click.
_seat = {"username": "demo-admin"}


def seat_user():
  """Return the current demo seat user, seeding the demo on first use."""
  if not current_app.config.get("DEMO_MODE"):
    return None
  _seed()
  return get_user_by_username(db(), _seat["username"])


def _ensure_user(username: str, display_name: str, role: Role):
  user = get_user_by_username(db(), username)
  if user is None:
    user = create_user(db(), username, display_name, at=now())
  assign_role(db(), user.id, role, at=now())
  return user


def _next_id(table: str) -> int:
  row = (
    db()
    .exec_driver_sql(f"SELECT COALESCE(MAX(id), 0) + 1 AS next FROM {table}")
    .fetchone()
  )
  return row._mapping["next"]


def _seed() -> None:
  admin = _ensure_user("demo-admin", "Demo Admin", Role.ADMIN)
  Mara = _ensure_user("demo-Mara", "Demo Requester", Role.REQUESTER)
  Sam = _ensure_user("demo-Sam", "Demo Assignee", Role.ASSIGNEE)
  if not requests_data.list_requests(db()):
    requests_data.save(
      db(),
      Request(
        id=_next_id("requests"),
        title="Broken projector in Room 4",
        description="The projector powers on, then drops the image after two minutes.",
        requester_id=Mara.id,
        priority_suggestion=Priority.HIGH,
        domains=("Facilities", "Room 4"),
        created_at=now(),
        updated_at=now(),
      ),
    )
    requests_data.save(
      db(),
      Request(
        id=_next_id("requests"),
        title="Ideas for the next community day",
        description="Collect activity ideas for the next community day.",
        requester_id=admin.id,
        priority_suggestion=Priority.MEDIUM,
        visibility=Visibility.PUBLIC,
        domains=("Community",),
        created_at=now(),
        updated_at=now(),
      ),
    )
  if not issues_data.list_issues(db()):
    issues_data.save(
      db(),
      Issue(
        id=_next_id("issues"),
        title="Projector repair plan",
        description="Check the lamp hours, swap the cable, then test with a class laptop.",
        requester_id=Mara.id,
        assignee_id=Sam.id,
        priority=Priority.HIGH,
        domains=("Facilities", "Room 4"),
        created_at=now(),
        updated_at=now(),
      ),
    )


def _enter(username: str, endpoint: str) -> Response:
  user = get_user_by_username(db(), username)
  issued = create_session(db(), user.id, at=now())
  response = redirect(url_for(endpoint))
  response.set_cookie(
    SESSION_COOKIE,
    issued.token,
    httponly=True,
    secure=True,
    samesite="None",
    partitioned=True,
    max_age=int(SESSION_TTL.total_seconds()),
    path="/",
  )
  return response


@bp.get("/demo")
def demo() -> Response:
  """Open a seeded demo session without credentials when demo mode is on."""
  if not current_app.config.get("DEMO_MODE"):
    abort(404)
  _seed()
  _seat["username"] = "demo-admin"
  return _enter("demo-admin", "records.workspace")


@bp.get("/demo/switch/<role>")
def switch(role: str) -> Response:
  """Swap the demo seat between the staff and client demo users."""
  if not current_app.config.get("DEMO_MODE"):
    abort(404)
  _seed()
  if role == "client":
    _seat["username"] = "demo-Mara"
    return _enter("demo-Mara", "pages.home")
  _seat["username"] = "demo-admin"
  return _enter("demo-admin", "records.workspace")
