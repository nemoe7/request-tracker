"""Retained notifications and per-user notification preferences."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Connection, Row

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


def _row_to_preference(category: str, row: Row | None) -> Preference:
  if row is None:
    return Preference(category)
  return Preference(
    category,
    enabled=bool(row._mapping["enabled"]),
    inbox_enabled=bool(row._mapping["inbox_enabled"]),
    pip_enabled=bool(row._mapping["pip_enabled"]),
  )


def preference(db: Connection, user_id: int, category: str) -> Preference:
  row = db.exec_driver_sql(
    "SELECT * FROM notification_preferences WHERE user_id = ? AND category = ?",
    (user_id, category),
  ).fetchone()
  return _row_to_preference(category, row)


def preferences(db: Connection, user_id: int) -> list[Preference]:
  marks = ", ".join("?" for _ in CATEGORIES)
  rows = db.exec_driver_sql(
    "SELECT * FROM notification_preferences "
    f"WHERE user_id = ? AND category IN ({marks})",
    (user_id, *CATEGORIES),
  ).fetchall()
  found = {row._mapping["category"]: row for row in rows}
  return [_row_to_preference(category, found.get(category)) for category in CATEGORIES]


def set_preference(
  db: Connection,
  user_id: int,
  category: str,
  *,
  enabled: bool,
  inbox_enabled: bool,
  pip_enabled: bool,
) -> None:
  if category not in CATEGORIES:
    raise ValueError(f"unknown notification category: {category}")
  db.exec_driver_sql(
    "INSERT INTO notification_preferences "
    "(user_id, category, enabled, inbox_enabled, pip_enabled) VALUES (?, ?, ?, ?, ?) "
    "ON CONFLICT(user_id, category) DO UPDATE SET enabled = excluded.enabled, "
    "inbox_enabled = excluded.inbox_enabled, pip_enabled = excluded.pip_enabled",
    (user_id, category, int(enabled), int(inbox_enabled), int(pip_enabled)),
  )
  db.commit()


def notify(
  db: Connection,
  user_id: int,
  category: str,
  message: str,
  *,
  at: datetime,
  object_type: str | None = None,
  object_id: int | None = None,
  actor_id: int | None = None,
  commit: bool = True,
) -> Notification | None:
  """Store one notice when the recipient keeps that category in the inbox."""
  picked = preference(db, user_id, category)
  if not picked.enabled or not picked.inbox_enabled:
    return None
  cursor = db.exec_driver_sql(
    "INSERT INTO notifications "
    "(user_id, category, object_type, object_id, message, actor_id, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    (user_id, category, object_type, object_id, message, actor_id, pack_time(at)),
  )
  if commit:
    db.commit()
  row = db.exec_driver_sql(
    "SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)
  ).fetchone()
  return _from_row(row)


def list_for_user(
  db: Connection, user_id: int, *, limit: int = 100
) -> list[Notification]:
  rows = db.exec_driver_sql(
    "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?",
    (user_id, limit),
  )
  return [_from_row(row) for row in rows]


def count_for_user(db: Connection, user_id: int) -> int:
  row = db.exec_driver_sql(
    "SELECT COUNT(*) AS count FROM notifications WHERE user_id = ?", (user_id,)
  ).fetchone()
  return row._mapping["count"]


def delete_for_user(db: Connection, user_id: int, notice_id: int) -> bool:
  cursor = db.exec_driver_sql(
    "DELETE FROM notifications WHERE id = ? AND user_id = ?",
    (notice_id, user_id),
  )
  db.commit()
  return cursor.rowcount > 0


def delete_all_for_user(db: Connection, user_id: int) -> int:
  cursor = db.exec_driver_sql("DELETE FROM notifications WHERE user_id = ?", (user_id,))
  db.commit()
  return cursor.rowcount


def pip_visible(db: Connection, user_id: int) -> bool:
  return any(item.pip_enabled and item.enabled for item in preferences(db, user_id))


def _from_row(row: Row) -> Notification:
  return Notification(
    id=row._mapping["id"],
    user_id=row._mapping["user_id"],
    category=row._mapping["category"],
    object_type=row._mapping["object_type"],
    object_id=row._mapping["object_id"],
    message=row._mapping["message"],
    actor_id=row._mapping["actor_id"],
    created_at=unpack_time(row._mapping["created_at"]),
  )
