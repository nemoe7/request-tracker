"""Which items a staff member opened. The workspace reads it as an inbox."""

from datetime import datetime

from sqlalchemy.engine import Connection

from ._rows import pack_time


def mark(
  db: Connection, user_id: int, object_type: str, object_id: int, *, at: datetime
) -> None:
  """Remember that this person opened the item."""
  db.exec_driver_sql(
    "INSERT OR IGNORE INTO workspace_reads (user_id, object_type, object_id, read_at) "
    "VALUES (?, ?, ?, ?)",
    (user_id, object_type, object_id, pack_time(at)),
  )
  db.commit()


def read_ids(db: Connection, user_id: int, object_type: str) -> set[int]:
  """Return the ids of the items this person opened."""
  rows = db.exec_driver_sql(
    "SELECT object_id FROM workspace_reads WHERE user_id = ? AND object_type = ?",
    (user_id, object_type),
  ).fetchall()
  return {row._mapping["object_id"] for row in rows}
