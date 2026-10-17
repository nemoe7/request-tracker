"""One-time, expiring enrollment tokens. The database stores only hashes."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.engine import Connection, Row

from pwedepa._tokens import hash_token, new_token
from pwedepa.data._rows import pack_time, unpack_time

from .audit import record_audit
from .errors import InvalidToken
from .grants import Role

ENROLLMENT_TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class EnrollmentToken:
  id: int
  role: Role
  created_at: datetime | None
  expires_at: datetime | None
  used_at: datetime | None


@dataclass(frozen=True)
class IssuedEnrollmentToken:
  record: EnrollmentToken
  token: str


def issue_enrollment_token(
  db: Connection,
  *,
  role: Role,
  at: datetime,
  ttl: timedelta = ENROLLMENT_TOKEN_TTL,
  actor_id: int | None = None,
) -> IssuedEnrollmentToken:
  """Issue the plaintext token once. The database stores only its hash."""
  token = new_token()
  cursor = db.exec_driver_sql(
    "INSERT INTO enrollment_tokens (role, token_hash, created_at, expires_at) "
    "VALUES (?, ?, ?, ?)",
    (role.value, hash_token(token), pack_time(at), pack_time(at + ttl)),
  )
  record_audit(
    db,
    "enrollment_token.issued",
    at=at,
    actor_id=actor_id,
    object_type="enrollment_token",
    object_id=cursor.lastrowid,
    data={"role": role.value},
    commit=False,
  )
  db.commit()
  return IssuedEnrollmentToken(_get_record(db, cursor.lastrowid), token)


def has_waiting(db: Connection, *, at: datetime) -> bool:
  row = db.exec_driver_sql(
    "SELECT 1 FROM enrollment_tokens WHERE used_at IS NULL AND expires_at > ? LIMIT 1",
    (pack_time(at),),
  ).fetchone()
  return row is not None


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
    actor_id=None,
    object_type="enrollment_token",
    object_id=record.id,
    data={"role": record.role.value},
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
    role=Role(row._mapping["role"]),
    created_at=unpack_time(row._mapping["created_at"]),
    expires_at=unpack_time(row._mapping["expires_at"]),
    used_at=unpack_time(row._mapping["used_at"]),
  )
