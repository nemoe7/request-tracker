import json

from sqlalchemy.engine import Connection

from pwedepa.core import Event

from ._rows import pack_time, unpack_time


def append(
  db: Connection, object_type: str, object_id: int, event: Event, *, commit: bool = True
) -> None:
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
  db.exec_driver_sql(
    "DELETE FROM workspace_reads WHERE object_type = ? AND object_id = ?",
    (object_type, object_id),
  )
  if commit:
    db.commit()


def newest_comments(
  db: Connection, object_type: str, object_ids: list[int]
) -> dict[int, Event]:
  """The newest comment per record, keyed by record id."""
  if not object_ids:
    return {}
  marks = ", ".join("?" for _ in object_ids)
  rows = db.exec_driver_sql(
    "SELECT * FROM events WHERE object_type = ? AND event_type = ? "
    f"AND object_id IN ({marks}) ORDER BY id",
    (object_type, f"{object_type}.comment", *object_ids),
  )
  newest: dict[int, Event] = {}
  for row in rows:
    newest[row._mapping["object_id"]] = Event(
      event_type=row._mapping["event_type"],
      actor_id=row._mapping["actor_id"],
      at=unpack_time(row._mapping["at"]),
      data=json.loads(row._mapping["data"]),
    )
  return newest


def list_for(
  db: Connection, object_type: str, object_id: int, *, limit: int | None = None
) -> list[Event]:
  """Oldest first. A limit keeps the newest of them."""
  query = "SELECT * FROM events WHERE object_type = ? AND object_id = ? ORDER BY id"
  params: tuple = (object_type, object_id)
  if limit is not None:
    # The tail must come from the far end of the table, so read it backwards.
    query = "SELECT * FROM events WHERE object_type = ? AND object_id = ? ORDER BY id DESC LIMIT ?"
    params = (object_type, object_id, limit)
  rows = list(db.exec_driver_sql(query, params))
  if limit is not None:
    rows.reverse()
  return [
    Event(
      event_type=row._mapping["event_type"],
      actor_id=row._mapping["actor_id"],
      at=unpack_time(row._mapping["at"]),
      data=json.loads(row._mapping["data"]),
    )
    for row in rows
  ]
