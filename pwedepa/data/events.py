"""Append and read activity events in SQLite."""

import json

from sqlalchemy.engine import Connection

from pwedepa.core import Event

from ._rows import pack_time, unpack_time


def append(db: Connection, object_type: str, object_id: int, event: Event) -> None:
  db.exec_driver_sql(
    "INSERT INTO events (object_type, object_id, event_type, actor_id, at, data) "
    "VALUES (?, ?, ?, ?, ?, ?)",
    (
      object_type,
      object_id,
      event.event_type,
      event.actor_id,
      pack_time(event.at),
      json.dumps(event.data),
    ),
  )
  db.commit()


def list_for(db: Connection, object_type: str, object_id: int) -> list[Event]:
  rows = db.exec_driver_sql(
    "SELECT * FROM events WHERE object_type = ? AND object_id = ? ORDER BY id",
    (object_type, object_id),
  )
  return [
    Event(
      event_type=row._mapping["event_type"],
      actor_id=row._mapping["actor_id"],
      at=unpack_time(row._mapping["at"]),
      data=json.loads(row._mapping["data"]),
    )
    for row in rows
  ]
