"""Append and read activity events in SQLite."""

import json
import sqlite3

from pwedepa.core import Event

from ._rows import pack_time, unpack_time


def append(
  db: sqlite3.Connection, object_type: str, object_id: int, event: Event
) -> None:
  db.execute(
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


def list_for(db: sqlite3.Connection, object_type: str, object_id: int) -> list[Event]:
  rows = db.execute(
    "SELECT * FROM events WHERE object_type = ? AND object_id = ? ORDER BY id",
    (object_type, object_id),
  )
  return [
    Event(
      event_type=row["event_type"],
      actor_id=row["actor_id"],
      at=unpack_time(row["at"]),
      data=json.loads(row["data"]),
    )
    for row in rows
  ]
