"""User records and account lifecycle."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

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


def create_user(
  db: sqlite3.Connection,
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
    cursor = db.execute(
      "INSERT INTO users (username, display_name, status, created_at, updated_at) "
      "VALUES (?, ?, ?, ?, ?)",
      (username, display_name, UserStatus.ACTIVE.value, pack_time(at), pack_time(at)),
    )
  except sqlite3.IntegrityError as exc:
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


def get_user(db: sqlite3.Connection, user_id: int) -> User | None:
  row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
  return None if row is None else _from_row(row)


def get_user_by_username(db: sqlite3.Connection, username: str) -> User | None:
  row = db.execute(
    "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username.strip(),)
  ).fetchone()
  return None if row is None else _from_row(row)


def list_users(db: sqlite3.Connection, *, include_archived: bool = False) -> list[User]:
  query = "SELECT * FROM users"
  if not include_archived:
    query += " WHERE archived_at IS NULL"
  query += " ORDER BY id"
  return [_from_row(row) for row in db.execute(query)]


def archive_user(
  db: sqlite3.Connection, user_id: int, *, at: datetime, actor_id: int | None = None
) -> User:
  """Archive a user. Historical records keep pointing at the user."""
  user = _require_user(db, user_id)
  if user.status is UserStatus.ARCHIVED:
    return user
  db.execute(
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
    commit=False,
  )
  db.commit()
  return get_user(db, user_id)


def reactivate_user(
  db: sqlite3.Connection, user_id: int, *, at: datetime, actor_id: int | None = None
) -> User:
  _require_user(db, user_id)
  db.execute(
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


def _require_user(db: sqlite3.Connection, user_id: int) -> User:
  user = get_user(db, user_id)
  if user is None:
    raise AuthError("the user does not exist")
  return user


def _from_row(row: sqlite3.Row) -> User:
  return User(
    id=row["id"],
    username=row["username"],
    display_name=row["display_name"],
    status=UserStatus(row["status"]),
    created_at=unpack_time(row["created_at"]),
    updated_at=unpack_time(row["updated_at"]),
    archived_at=unpack_time(row["archived_at"]),
  )
