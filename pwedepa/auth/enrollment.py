"""One-time, expiring enrollment tokens. The database stores only hashes."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.engine import Connection, Row

from pwedepa.data._rows import pack_time, unpack_time

from ._tokens import hash_token, new_token
from .audit import record_audit
from .errors import AuthenticationFailed, InvalidToken
from .users import UserStatus, get_user

ENROLLMENT_TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class EnrollmentToken:
  id: int
  user_id: int
  created_at: datetime | None
  expires_at: datetime | None
  used_at: datetime | None


@dataclass(frozen=True)
class IssuedEnrollmentToken:
  record: EnrollmentToken
  token: str


def issue_enrollment_token(
  db: Connection,
  user_id: int,
  *,
  at: datetime,
  ttl: timedelta = ENROLLMENT_TOKEN_TTL,
  actor_id: int | None = None,
) -> IssuedEnrollmentToken:
  """Issue the plaintext token once. The database stores only its hash."""
  user = get_user(db, user_id)
  if user is None or user.status is UserStatus.ARCHIVED:
    raise AuthenticationFailed("an enrollment token needs an active user")
  token = new_token()
  cursor = db.exec_driver_sql(
    "INSERT INTO enrollment_tokens (user_id, token_hash, created_at, expires_at) "
    "VALUES (?, ?, ?, ?)",
    (user_id, hash_token(token), pack_time(at), pack_time(at + ttl)),
  )
  record_audit(
    db,
    "enrollment_token.issued",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=user_id,
    commit=False,
  )
  db.commit()
  return IssuedEnrollmentToken(_get_record(db, cursor.lastrowid), token)


def validate_enrollment_token(
  db: Connection, token: str, *, at: datetime
) -> EnrollmentToken:
  record = _find_token(db, token)
  if record is None or record.used_at is not None:
    raise InvalidToken("the enrollment token is invalid or already used")
  if record.expires_at is None or record.expires_at <= at:
    raise InvalidToken("the enrollment token has expired")
  return record


def consume_enrollment_token(
  db: Connection, token: str, *, at: datetime
) -> EnrollmentToken:
  """Atomically claim a valid token so concurrent requests cannot reuse it."""
  cursor = db.exec_driver_sql(
    "UPDATE enrollment_tokens SET used_at = ? "
    "WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
    (pack_time(at), hash_token(token), pack_time(at)),
  )
  if cursor.rowcount != 1:
    db.rollback()
    raise InvalidToken("the enrollment token is invalid, expired, or already used")
  record = _find_token(db, token)
  record_audit(
    db,
    "enrollment_token.consumed",
    at=at,
    actor_id=record.user_id,
    object_type="user",
    object_id=record.user_id,
    commit=False,
  )
  db.commit()
  return record


def _find_token(db: Connection, token: str) -> EnrollmentToken | None:
  row = db.exec_driver_sql(
    "SELECT * FROM enrollment_tokens WHERE token_hash = ?", (hash_token(token),)
  ).fetchone()
  return None if row is None else _from_row(row)


def _get_record(db: Connection, token_id: int) -> EnrollmentToken:
  row = db.exec_driver_sql(
    "SELECT * FROM enrollment_tokens WHERE id = ?", (token_id,)
  ).fetchone()
  return _from_row(row)


def _from_row(row: Row) -> EnrollmentToken:
  return EnrollmentToken(
    id=row._mapping["id"],
    user_id=row._mapping["user_id"],
    created_at=unpack_time(row._mapping["created_at"]),
    expires_at=unpack_time(row._mapping["expires_at"]),
    used_at=unpack_time(row._mapping["used_at"]),
  )
