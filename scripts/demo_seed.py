"""Seed a demo database with people, records, activity, and notices.

The demo seats keep the usernames the demo seat module already uses. Seeding
an app database first keeps its own seed out of the way.
"""

from datetime import UTC, datetime, timedelta

from pwedepa.auth import Role, assign_role, get_user_by_username, users
from pwedepa.core import (
  Event,
  Issue,
  IssueStatus,
  Priority,
  Request,
  RequestStatus,
  Visibility,
)
from pwedepa.data import db as data_db
from pwedepa.data import events, issues, notifications, requests
from pwedepa.data.domains import domain_slot, starter_domains


def _user(db, username, display, role, at):
  person = get_user_by_username(db, username)
  if person is None:
    person = users.create_user(db, username, display, at=at)
  assign_role(db, person.id, role, at=at)
  return person


def seed(db, *, now: datetime, db_path=None) -> dict:
  """Fill one connected database with the demo cast. Return the people."""
  admin = _user(db, "demo-admin", "Demo Admin", Role.ADMIN, now)
  Mara = _user(db, "demo-Mara", "Demo Requester", Role.REQUESTER, now)
  Sam = _user(db, "demo-Sam", "Demo Assignee", Role.ASSIGNEE, now)
  Priya = _user(db, "Priya", "Priya Nair", Role.REQUESTER, now)
  Ben = _user(db, "Ben", "Ben Ortiz", Role.ASSIGNEE, now)
  people = {"admin": admin, "Mara": Mara, "Sam": Sam, "Priya": Priya, "Ben": Ben}

  names = starter_domains(db_path)

  def at(days: float, hours: float = 0) -> datetime:
    return now - timedelta(days=days, hours=hours)

  request_rows = [
    Request(
      id=1,
      title="Broken projector in Room 4",
      description="The projector powers on, then drops the image after two minutes.",
      requester_id=Mara.id,
      priority_suggestion=Priority.HIGH,
      domains=(domain_slot(names, 0), domain_slot(names, 1)),
      created_at=at(4, 2),
      updated_at=at(0, 3),
    ),
    Request(
      id=2,
      title="Ideas for the next community day",
      description="Collect activity ideas for the next community day.",
      requester_id=admin.id,
      priority_suggestion=Priority.MEDIUM,
      visibility=Visibility.PUBLIC,
      domains=(domain_slot(names, 4),),
      created_at=at(3, 5),
      updated_at=at(1, 1),
    ),
    Request(
      id=3,
      title="Whiteboard markers for the studio",
      description="The studio board needs fresh markers before the Friday workshop.",
      status=RequestStatus.PENDING,
      requester_id=Mara.id,
      priority_suggestion=Priority.MEDIUM,
      visibility=Visibility.PUBLIC,
      domains=(domain_slot(names, 2),),
      created_at=at(2, 4),
      updated_at=at(0, 6),
    ),
    Request(
      id=4,
      title="Replace the hallway lights",
      description="Two hallway tubes flicker through the afternoon.",
      status=RequestStatus.DELAYED,
      requester_id=admin.id,
      priority_suggestion=Priority.LOW,
      domains=(domain_slot(names, 0),),
      created_at=at(6, 1),
      updated_at=at(2, 2),
    ),
    Request(
      id=5,
      title="Laptop for the new facilitator",
      description="The incoming facilitator needs a laptop before Monday onboarding.",
      requester_id=Priya.id,
      priority_suggestion=Priority.HIGH,
      visibility=Visibility.PUBLIC,
      domains=(domain_slot(names, 5),),
      created_at=at(1, 3),
      updated_at=at(0, 2),
    ),
    Request(
      id=6,
      title="Extend Friday hours for exam week",
      description="Students asked for two extra evening hours during exam week.",
      status=RequestStatus.RAISED,
      requester_id=Priya.id,
      priority_suggestion=Priority.URGENT,
      visibility=Visibility.PUBLIC,
      domains=(domain_slot(names, 1),),
      created_at=at(0, 8),
      updated_at=at(0, 8),
    ),
    Request(
      id=7,
      title="Print the October schedule",
      description="Print forty copies of the October schedule for the front desk.",
      status=RequestStatus.FULFILLED,
      requester_id=Mara.id,
      priority_suggestion=Priority.LOW,
      domains=(domain_slot(names, 3),),
      created_at=at(9, 2),
      updated_at=at(7, 4),
    ),
    Request(
      id=8,
      title="Borrow the sound system",
      description="The reading group asked to borrow the sound system on Sunday.",
      status=RequestStatus.REJECTED,
      requester_id=Priya.id,
      priority_suggestion=Priority.MEDIUM,
      domains=(domain_slot(names, 4),),
      created_at=at(8, 3),
      updated_at=at(7, 6),
    ),
  ]
  for record in request_rows:
    requests.save(db, record)
    events.append(
      db,
      "request",
      record.id,
      Event("request.created", record.requester_id, record.created_at),
    )

  issue_rows = [
    Issue(
      id=1,
      title="Projector repair plan",
      description="Check the lamp hours, swap the cable, then test with a class laptop.",
      source_request_id=1,
      requester_id=Mara.id,
      assignee_id=Sam.id,
      priority=Priority.HIGH,
      domains=(domain_slot(names, 0), domain_slot(names, 5)),
      created_at=at(4, 1),
      updated_at=at(0, 3),
    ),
    Issue(
      id=2,
      title="Door hinge replacement",
      description="The storage door sticks because the top hinge is bent.",
      status=IssueStatus.BLOCKED,
      requester_id=Mara.id,
      assignee_id=Ben.id,
      priority=Priority.URGENT,
      domains=(domain_slot(names, 1),),
      created_at=at(3, 2),
      updated_at=at(0, 5),
    ),
    Issue(
      id=3,
      title="Reset the mail filter",
      description="The shared inbox filter sent two client notes to spam.",
      status=IssueStatus.RESOLVED,
      requester_id=admin.id,
      assignee_id=Sam.id,
      priority=Priority.MEDIUM,
      visibility=Visibility.PUBLIC,
      domains=(domain_slot(names, 2),),
      created_at=at(5, 4),
      updated_at=at(2, 3),
    ),
    Issue(
      id=4,
      title="Retire the old wiki",
      description="The old wiki now points readers to the current handbook.",
      status=IssueStatus.CLOSED,
      requester_id=admin.id,
      assignee_id=Ben.id,
      priority=Priority.LOW,
      domains=(domain_slot(names, 3),),
      created_at=at(12, 2),
      updated_at=at(9, 1),
    ),
    Issue(
      id=5,
      title="Fix the leaking faucet",
      description="The pantry faucet drips all day and the cabinet below stays damp.",
      requester_id=Priya.id,
      assignee_id=Ben.id,
      priority=Priority.MEDIUM,
      domains=(domain_slot(names, 5),),
      created_at=at(1, 6),
      updated_at=at(0, 4),
    ),
    Issue(
      id=6,
      title="Update the room booking sheet",
      description="The booking sheet still lists the old room names.",
      status=IssueStatus.BLOCKED,
      requester_id=Priya.id,
      assignee_id=Sam.id,
      priority=Priority.HIGH,
      domains=(domain_slot(names, 4),),
      created_at=at(2, 1),
      updated_at=at(1, 2),
    ),
    Issue(
      id=7,
      title="Repaint the studio wall",
      description="The studio wall needs one fresh coat before the exhibit opens.",
      status=IssueStatus.RESOLVED,
      requester_id=Mara.id,
      assignee_id=Ben.id,
      priority=Priority.LOW,
      visibility=Visibility.PUBLIC,
      domains=(domain_slot(names, 2),),
      created_at=at(7, 3),
      updated_at=at(3, 3),
    ),
    Issue(
      id=8,
      title="Archive the 2024 photo drive",
      description="Move the 2024 photos to the archive drive and check the backup.",
      status=IssueStatus.CLOSED,
      requester_id=admin.id,
      assignee_id=Sam.id,
      priority=Priority.MEDIUM,
      domains=(domain_slot(names, 3),),
      created_at=at(15, 5),
      updated_at=at(10, 2),
    ),
  ]
  for record in issue_rows:
    issues.save(db, record)
    events.append(
      db,
      "issue",
      record.id,
      Event("issue.created", record.assignee_id, record.created_at),
    )

  events.append(
    db,
    "request",
    1,
    Event(
      "request.comment",
      Mara.id,
      at(0, 3),
      {"text": "The class starts at nine, so a morning check helps."},
    ),
  )
  events.append(
    db,
    "request",
    5,
    Event(
      "request.comment",
      Priya.id,
      at(0, 2),
      {"text": "Any spare charger helps while the new one ships."},
    ),
  )
  events.append(
    db,
    "issue",
    1,
    Event(
      "issue.comment",
      Sam.id,
      at(0, 3),
      {"text": "The lamp counter reads 1,900 hours. A swap comes first."},
    ),
  )
  events.append(
    db,
    "issue",
    2,
    Event(
      "issue.state_changed",
      Ben.id,
      at(0, 5),
      {"from": "OPEN", "to": "BLOCKED"},
    ),
  )
  events.append(
    db,
    "issue",
    2,
    Event(
      "issue.comment",
      Ben.id,
      at(0, 5),
      {"text": "Waiting for the replacement hinge."},
    ),
  )
  events.append(
    db,
    "issue",
    5,
    Event(
      "issue.comment",
      Ben.id,
      at(0, 4),
      {"text": "The shutoff valve holds. The washer swap is next."},
    ),
  )

  notifications.notify(
    db,
    admin.id,
    "activity",
    "Priya Nair opened Laptop for the new facilitator",
    at=at(1, 3),
    object_type="request",
    object_id=5,
    actor_id=Priya.id,
  )
  notifications.notify(
    db,
    admin.id,
    "comments",
    "Demo Requester commented on Broken projector in Room 4",
    at=at(0, 3),
    object_type="request",
    object_id=1,
    actor_id=Mara.id,
  )
  notifications.notify(
    db,
    Mara.id,
    "activity",
    "Demo Assignee commented on Projector repair plan",
    at=at(0, 3),
    object_type="issue",
    object_id=1,
    actor_id=Sam.id,
  )
  notifications.notify(
    db,
    admin.id,
    "sharing",
    "Demo Requester shared Ideas for the next community day with you",
    at=at(1, 1),
    object_type="request",
    object_id=2,
    actor_id=Mara.id,
  )
  return people


def seed_file(path) -> dict:
  """Seed the database file at path. Return the demo people."""
  database = data_db.connect(path)
  try:
    return seed(database, now=datetime.now(UTC), db_path=path)
  finally:
    database.close()


if __name__ == "__main__":
  import sys

  seed_file(sys.argv[1])
  print(f"seeded {sys.argv[1]}")
