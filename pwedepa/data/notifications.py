"""Retained notifications and per-user notification preferences."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ._rows import pack_time, unpack_time

CATEGORIES = ("activity", "comments", "sharing")


@dataclass(frozen=True)
class Notification:
  id: int
  user_id: int
  category: str
  object_type: str | None
  object_id: int | None
  message: str
  actor_id: int | None
  created_at: datetime | None


@dataclass(frozen=True)
class Preference:
  category: str
  enabled: bool = True
  inbox_enabled: bool = True
  pip_enabled: bool = True


def preference(db: sqlite3.Connection, user_id: int, category: str) -> Preference:
  row = db.execute(
    "SELECT * FROM notification_preferences WHERE user_id = ? AND category = ?",
    (user_id, category),
  ).fetchone()
  if row is None:
    return Preference(category)
  return Preference(
    category,
    enabled=bool(row["enabled"]),
    inbox_enabled=bool(row["inbox_enabled"]),
    pip_enabled=bool(row["pip_enabled"]),
  )


def preferences(db: sqlite3.Connection, user_id: int) -> list[Preference]:
  return [preference(db, user_id, category) for category in CATEGORIES]


def set_preference(
  db: sqlite3.Connection,
  user_id: int,
  category: str,
  *,
  enabled: bool,
  inbox_enabled: bool,
  pip_enabled: bool,
) -> None:
  if category not in CATEGORIES:
    raise ValueError(f"unknown notification category: {category}")
  db.execute(
    "INSERT INTO notification_preferences "
    "(user_id, category, enabled, inbox_enabled, pip_enabled) VALUES (?, ?, ?, ?, ?) "
    "ON CONFLICT(user_id, category) DO UPDATE SET enabled = excluded.enabled, "
    "inbox_enabled = excluded.inbox_enabled, pip_enabled = excluded.pip_enabled",
    (user_id, category, int(enabled), int(inbox_enabled), int(pip_enabled)),
  )
  db.commit()


def notify(
  db: sqlite3.Connection,
  user_id: int,
  category: str,
  message: str,
  *,
  at: datetime,
  object_type: str | None = None,
  object_id: int | None = None,
  actor_id: int | None = None,
) -> Notification | None:
  """Store one notice when the recipient keeps that category in the inbox."""
  picked = preference(db, user_id, category)
  if not picked.enabled or not picked.inbox_enabled:
    return None
  cursor = db.execute(
    "INSERT INTO notifications "
    "(user_id, category, object_type, object_id, message, actor_id, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    (user_id, category, object_type, object_id, message, actor_id, pack_time(at)),
  )
  db.commit()
  row = db.execute(
    "SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)
  ).fetchone()
  return _from_row(row)


def list_for_user(
  db: sqlite3.Connection, user_id: int, *, limit: int = 100
) -> list[Notification]:
  rows = db.execute(
    "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?",
    (user_id, limit),
  )
  return [_from_row(row) for row in rows]


def count_for_user(db: sqlite3.Connection, user_id: int) -> int:
  row = db.execute(
    "SELECT COUNT(*) AS count FROM notifications WHERE user_id = ?", (user_id,)
  ).fetchone()
  return row["count"]


def pip_visible(db: sqlite3.Connection, user_id: int) -> bool:
  """True when at least one category may show the top-bar pip."""
  return any(item.pip_enabled and item.enabled for item in preferences(db, user_id))


def _from_row(row: sqlite3.Row) -> Notification:
  return Notification(
    id=row["id"],
    user_id=row["user_id"],
    category=row["category"],
    object_type=row["object_type"],
    object_id=row["object_id"],
    message=row["message"],
    actor_id=row["actor_id"],
    created_at=unpack_time(row["created_at"]),
  )
