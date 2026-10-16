"""The one active landing-page message."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ._rows import pack_time, unpack_time


@dataclass(frozen=True)
class SiteMessage:
  id: int
  message: str
  enabled: bool
  created_at: datetime | None
  updated_at: datetime | None
  expires_at: datetime | None
  created_by_id: int | None


def save_message(
  db: sqlite3.Connection,
  message: str,
  *,
  at: datetime,
  created_by_id: int | None,
  enabled: bool = True,
  expires_at: datetime | None = None,
) -> SiteMessage:
  """Replace the current message with a new one."""
  db.execute("UPDATE site_messages SET enabled = 0, updated_at = ?", (pack_time(at),))
  cursor = db.execute(
    "INSERT INTO site_messages "
    "(message, enabled, created_at, updated_at, expires_at, created_by_id) "
    "VALUES (?, ?, ?, ?, ?, ?)",
    (
      message,
      int(enabled),
      pack_time(at),
      pack_time(at),
      pack_time(expires_at),
      created_by_id,
    ),
  )
  db.commit()
  row = db.execute(
    "SELECT * FROM site_messages WHERE id = ?", (cursor.lastrowid,)
  ).fetchone()
  return _from_row(row)


def get_active(db: sqlite3.Connection, at: datetime) -> SiteMessage | None:
  row = db.execute(
    "SELECT * FROM site_messages WHERE enabled = 1 "
    "AND (expires_at IS NULL OR expires_at > ?) ORDER BY id DESC LIMIT 1",
    (pack_time(at),),
  ).fetchone()
  return None if row is None else _from_row(row)


def list_messages(db: sqlite3.Connection) -> list[SiteMessage]:
  rows = db.execute("SELECT * FROM site_messages ORDER BY id DESC")
  return [_from_row(row) for row in rows]


def _from_row(row: sqlite3.Row) -> SiteMessage:
  return SiteMessage(
    id=row["id"],
    message=row["message"],
    enabled=bool(row["enabled"]),
    created_at=unpack_time(row["created_at"]),
    updated_at=unpack_time(row["updated_at"]),
    expires_at=unpack_time(row["expires_at"]),
    created_by_id=row["created_by_id"],
  )
