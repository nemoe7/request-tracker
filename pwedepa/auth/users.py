"""User accounts and their lifecycle."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy.engine import Connection, Row
from sqlalchemy.exc import IntegrityError

from pwedepa.data._rows import pack_time, unpack_time

from .audit import record_audit
from .errors import AuthError


class UserStatus(str, Enum):
  ACTIVE = "ACTIVE"
  ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class User:
  id: int
  username: str
  display_name: str
  status: UserStatus
  created_at: datetime | None
  updated_at: datetime | None
  archived_at: datetime | None


def count_users(db: Connection) -> int:
  row = db.exec_driver_sql("SELECT COUNT(*) AS count FROM users").fetchone()
  return row._mapping["count"]


def create_user(
  db: Connection,
  username: str,
  display_name: str,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> User:
  """Create an active user with a case-insensitively unique username."""
  username = username.strip()
  display_name = display_name.strip()
  if not username or not display_name:
    raise AuthError("a user needs a username and a display name")
  try:
    cursor = db.exec_driver_sql(
      "INSERT INTO users (username, display_name, status, created_at, updated_at) "
      "VALUES (?, ?, ?, ?, ?)",
      (username, display_name, UserStatus.ACTIVE.value, pack_time(at), pack_time(at)),
    )
  except IntegrityError as exc:
    db.rollback()
    raise AuthError("the username is already in use") from exc
  record_audit(
    db,
    "user.created",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=cursor.lastrowid,
    data={"username": username},
    commit=False,
  )
  db.commit()
  return get_user(db, cursor.lastrowid)


def update_display_name(
  db: Connection,
  user_id: int,
  display_name: str,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> User:
  display_name = display_name.strip()
  if not display_name:
    raise AuthError("a user needs a display name")
  _require_user(db, user_id)
  db.exec_driver_sql(
    "UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?",
    (display_name, pack_time(at), user_id),
  )
  record_audit(
    db,
    "user.display_name_changed",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=user_id,
    data={"display_name": display_name},
    commit=False,
  )
  db.commit()
  return get_user(db, user_id)


def update_username(
  db: Connection,
  user_id: int,
  username: str,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> User:
  """Rename one user. Refuse a taken name, whatever its case."""
  username = username.strip()
  if not username:
    raise AuthError("a user needs a username")
  _require_user(db, user_id)
  taken = get_user_by_username(db, username)
  if taken is not None and taken.id != user_id:
    raise AuthError("the username is already in use")
  try:
    db.exec_driver_sql(
      "UPDATE users SET username = ?, updated_at = ? WHERE id = ?",
      (username, pack_time(at), user_id),
    )
  except IntegrityError as exc:
    db.rollback()
    raise AuthError("the username is already in use") from exc
  record_audit(
    db,
    "user.username_changed",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=user_id,
    data={"username": username},
    commit=False,
  )
  db.commit()
  return get_user(db, user_id)


def get_user(db: Connection, user_id: int) -> User | None:
  row = db.exec_driver_sql("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
  return None if row is None else _from_row(row)


def get_user_by_username(db: Connection, username: str) -> User | None:
  row = db.exec_driver_sql(
    "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
  ).fetchone()
  return None if row is None else _from_row(row)


def list_users(db: Connection, *, include_archived: bool = False) -> list[User]:
  query = "SELECT * FROM users"
  if not include_archived:
    query += " WHERE archived_at IS NULL"
  query += " ORDER BY id"
  return [_from_row(row) for row in db.exec_driver_sql(query)]


def archive_user(
  db: Connection,
  user_id: int,
  *,
  at: datetime,
  actor_id: int | None = None,
  reason: str | None = None,
) -> User:
  """Keep the row: past work still points at this user."""
  user = _require_user(db, user_id)
  if user.status is UserStatus.ARCHIVED:
    return user
  db.exec_driver_sql(
    "UPDATE users SET status = ?, archived_at = ?, updated_at = ? WHERE id = ?",
    (UserStatus.ARCHIVED.value, pack_time(at), pack_time(at), user_id),
  )
  record_audit(
    db,
    "user.archived",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=user_id,
    data={"reason": reason} if reason else None,
    commit=False,
  )
  db.commit()
  return get_user(db, user_id)


def reactivate_user(
  db: Connection, user_id: int, *, at: datetime, actor_id: int | None = None
) -> User:
  _require_user(db, user_id)
  db.exec_driver_sql(
    "UPDATE users SET status = ?, archived_at = NULL, updated_at = ? WHERE id = ?",
    (UserStatus.ACTIVE.value, pack_time(at), user_id),
  )
  record_audit(
    db,
    "user.reactivated",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=user_id,
    commit=False,
  )
  db.commit()
  return get_user(db, user_id)


def _require_user(db: Connection, user_id: int) -> User:
  user = get_user(db, user_id)
  if user is None:
    raise AuthError("the user does not exist")
  return user


def _from_row(row: Row) -> User:
  return User(
    id=row._mapping["id"],
    username=row._mapping["username"],
    display_name=row._mapping["display_name"],
    status=UserStatus(row._mapping["status"]),
    created_at=unpack_time(row._mapping["created_at"]),
    updated_at=unpack_time(row._mapping["updated_at"]),
    archived_at=unpack_time(row._mapping["archived_at"]),
  )
