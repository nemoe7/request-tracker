"""The demo seat. Demo mode stays off unless code asks for it."""

from flask import current_app

from pwedepa.auth import (
  Role,
  assign_role,
  create_user,
  get_user_by_username,
)
from pwedepa.core import Issue, Priority, Request, Visibility
from pwedepa.data import domains as domains_data
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.data.domains import domain_slot

from .. import now
from ._helpers import db

# The demo seat lives server-side. Preview frames can block the session
# cookie, and the demo must still open with one click. The frozen build sets
# the seat here per page set, so no URL opens or swaps it.
SEATS = {"staff": "demo-admin", "client": "demo-Mara"}
_seat = {"username": SEATS["staff"]}


def set_seat(role: str) -> None:
  """Aim the demo seat at a role. The Pages build sets it per page set."""
  _seat["username"] = SEATS[role]


def seat_user():
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


def _seed() -> None:
  names = domains_data.starter_domains(current_app.config["DATABASE"])
  admin = _ensure_user("demo-admin", "Demo Admin", Role.ADMIN)
  Mara = _ensure_user("demo-Mara", "Demo Requester", Role.REQUESTER)
  Sam = _ensure_user("demo-Sam", "Demo Assignee", Role.ASSIGNEE)
  if not requests_data.list_requests(db()):
    requests_data.save(
      db(),
      Request(
        id=0,
        title="Broken projector in Room 4",
        description="The projector powers on, then drops the image after two minutes.",
        requester_id=Mara.id,
        priority_suggestion=Priority.HIGH,
        domains=(domain_slot(names, 0), domain_slot(names, 1)),
        created_at=now(),
        updated_at=now(),
      ),
    )
    requests_data.save(
      db(),
      Request(
        id=0,
        title="Ideas for the next community day",
        description="Collect activity ideas for the next community day.",
        requester_id=admin.id,
        priority_suggestion=Priority.MEDIUM,
        visibility=Visibility.PUBLIC,
        domains=(domain_slot(names, 4),),
        created_at=now(),
        updated_at=now(),
      ),
    )
  if not issues_data.list_issues(db()):
    issues_data.save(
      db(),
      Issue(
        id=0,
        title="Projector repair plan",
        description="Check the lamp hours, swap the cable, then test with a class laptop.",
        requester_id=Mara.id,
        assignee_id=Sam.id,
        priority=Priority.HIGH,
        domains=(domain_slot(names, 2), domain_slot(names, 3)),
        created_at=now(),
        updated_at=now(),
      ),
    )
