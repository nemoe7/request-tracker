"""Server-side sessions with hashed, rotating, revocable tokens."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from pwedepa.data._rows import pack_time, unpack_time

from ._tokens import hash_token, new_token
from .audit import record_audit
from .errors import AuthenticationFailed, InvalidToken
from .users import UserStatus

SESSION_TTL = timedelta(days=30)


@dataclass(frozen=True)
class Session:
  id: int
  user_id: int
  created_at: datetime | None
  expires_at: datetime | None
  last_used_at: datetime | None
  revoked_at: datetime | None
  replaced_by_id: int | None


@dataclass(frozen=True)
class IssuedSession:
  session: Session
  token: str


def create_session(
  db: sqlite3.Connection,
  user_id: int,
  *,
  at: datetime,
  ttl: timedelta = SESSION_TTL,
) -> IssuedSession:
  """Create a session and return its plaintext token once."""
  _require_active_user(db, user_id)
  issued = _insert_session(db, user_id, at, ttl)
  record_audit(
    db,
    "session.created",
    at=at,
    actor_id=user_id,
    object_type="session",
    object_id=issued.session.id,
    commit=False,
  )
  db.commit()
  return issued


def resolve_session(
  db: sqlite3.Connection, token: str, *, at: datetime
) -> Session | None:
  """Return the active session for a token, or None when it cannot be used."""
  row = _find_token(db, token)
  if row is None or not _is_usable(db, row, at):
    return None
  db.execute(
    "UPDATE sessions SET last_used_at = ? WHERE id = ?",
    (pack_time(at), row["id"]),
  )
  db.commit()
  return _get_session(db, row["id"])


def rotate_session(
  db: sqlite3.Connection,
  token: str,
  *,
  at: datetime,
  ttl: timedelta = SESSION_TTL,
) -> IssuedSession:
  """Replace a session token. Reuse of a replaced token revokes its chain."""
  row = _find_token(db, token)
  if row is None:
    raise InvalidToken("the session token is invalid")
  if row["replaced_by_id"] is not None:
    _revoke_chain(db, row["id"], at)
    record_audit(
      db,
      "session.reuse_detected",
      at=at,
      actor_id=row["user_id"],
      object_type="session",
      object_id=row["id"],
      commit=False,
    )
    db.commit()
    raise AuthenticationFailed("session token reuse detected")
  if row["revoked_at"] is not None:
    raise AuthenticationFailed("the session has been revoked")
  if row["expires_at"] is None or unpack_time(row["expires_at"]) <= at:
    raise AuthenticationFailed("the session has expired")
  _require_active_user(db, row["user_id"])

  issued = _insert_session(db, row["user_id"], at, ttl)
  db.execute(
    "UPDATE sessions SET last_used_at = ?, replaced_by_id = ? WHERE id = ?",
    (pack_time(at), issued.session.id, row["id"]),
  )
  record_audit(
    db,
    "session.rotated",
    at=at,
    actor_id=row["user_id"],
    object_type="session",
    object_id=issued.session.id,
    data={"replaced_session_id": row["id"]},
    commit=False,
  )
  db.commit()
  return issued


def revoke_session(db: sqlite3.Connection, token: str, *, at: datetime) -> bool:
  row = _find_token(db, token)
  if row is None:
    return False
  cursor = db.execute(
    "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
    (pack_time(at), row["id"]),
  )
  if cursor.rowcount:
    record_audit(
      db,
      "session.revoked",
      at=at,
      actor_id=row["user_id"],
      object_type="session",
      object_id=row["id"],
      commit=False,
    )
  db.commit()
  return cursor.rowcount == 1


def revoke_user_sessions(db: sqlite3.Connection, user_id: int, *, at: datetime) -> int:
  cursor = db.execute(
    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
    (pack_time(at), user_id),
  )
  db.commit()
  return cursor.rowcount


def revoke_all_sessions(db: sqlite3.Connection, *, at: datetime) -> int:
  cursor = db.execute(
    "UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL",
    (pack_time(at),),
  )
  db.commit()
  return cursor.rowcount


def _insert_session(
  db: sqlite3.Connection, user_id: int, at: datetime, ttl: timedelta
) -> IssuedSession:
  token = new_token()
  cursor = db.execute(
    "INSERT INTO sessions (user_id, token_hash, created_at, expires_at, last_used_at) "
    "VALUES (?, ?, ?, ?, ?)",
    (
      user_id,
      hash_token(token),
      pack_time(at),
      pack_time(at + ttl),
      pack_time(at),
    ),
  )
  return IssuedSession(_get_session(db, cursor.lastrowid), token)


def _is_usable(db: sqlite3.Connection, row: sqlite3.Row, at: datetime) -> bool:
  if row["revoked_at"] is not None or row["replaced_by_id"] is not None:
    return False
  if row["expires_at"] is None or unpack_time(row["expires_at"]) <= at:
    return False
  user = db.execute(
    "SELECT status FROM users WHERE id = ?", (row["user_id"],)
  ).fetchone()
  return user is not None and user["status"] == UserStatus.ACTIVE.value


def _require_active_user(db: sqlite3.Connection, user_id: int) -> None:
  row = db.execute("SELECT status FROM users WHERE id = ?", (user_id,)).fetchone()
  if row is None or row["status"] != UserStatus.ACTIVE.value:
    raise AuthenticationFailed("sessions need an active user")


def _revoke_chain(db: sqlite3.Connection, session_id: int, at: datetime) -> None:
  current_id: int | None = session_id
  seen: set[int] = set()
  while current_id is not None and current_id not in seen:
    seen.add(current_id)
    row = db.execute(
      "SELECT replaced_by_id FROM sessions WHERE id = ?", (current_id,)
    ).fetchone()
    if row is None:
      return
    db.execute(
      "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
      (pack_time(at), current_id),
    )
    current_id = row["replaced_by_id"]


def _find_token(db: sqlite3.Connection, token: str) -> sqlite3.Row | None:
  return db.execute(
    "SELECT * FROM sessions WHERE token_hash = ?", (hash_token(token),)
  ).fetchone()


def _get_session(db: sqlite3.Connection, session_id: int) -> Session:
  row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
  return _from_row(row)


def _from_row(row: sqlite3.Row) -> Session:
  return Session(
    id=row["id"],
    user_id=row["user_id"],
    created_at=unpack_time(row["created_at"]),
    expires_at=unpack_time(row["expires_at"]),
    last_used_at=unpack_time(row["last_used_at"]),
    revoked_at=unpack_time(row["revoked_at"]),
    replaced_by_id=row["replaced_by_id"],
  )
