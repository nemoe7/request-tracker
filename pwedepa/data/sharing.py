"""Share links for Requests and Issues. The database stores token hashes."""

import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ._rows import pack_time, unpack_time

PERMISSIONS = ("VIEW", "COMMENT", "EDIT")


@dataclass(frozen=True)
class ShareLink:
  id: int
  object_type: str
  object_id: int
  permissions: tuple[str, ...]
  created_by_id: int
  created_at: datetime | None
  expires_at: datetime | None
  revoked_at: datetime | None
  view_consumed_at: datetime | None


@dataclass(frozen=True)
class IssuedShareLink:
  link: ShareLink
  token: str


def _hash(token: str) -> str:
  return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create(
  db: sqlite3.Connection,
  object_type: str,
  object_id: int,
  permissions,
  created_by_id: int,
  *,
  at: datetime,
  expires_at: datetime | None = None,
) -> IssuedShareLink:
  """Create a link and return its plain token once."""
  picked = {str(value).upper() for value in permissions}
  picked.add("VIEW")
  unknown = sorted(picked - set(PERMISSIONS))
  if unknown:
    raise ValueError(f"unknown share permissions: {', '.join(unknown)}")
  ordered = tuple(value for value in PERMISSIONS if value in picked)
  token = secrets.token_urlsafe(32)
  cursor = db.execute(
    "INSERT INTO share_links (object_type, object_id, token_hash, permissions, "
    "created_by_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (
      object_type,
      object_id,
      _hash(token),
      json.dumps(list(ordered)),
      created_by_id,
      pack_time(at),
      pack_time(expires_at),
    ),
  )
  db.commit()
  return IssuedShareLink(get(db, cursor.lastrowid), token)


def get(db: sqlite3.Connection, link_id: int) -> ShareLink | None:
  row = db.execute("SELECT * FROM share_links WHERE id = ?", (link_id,)).fetchone()
  return None if row is None else _from_row(row)


def find_by_token(db: sqlite3.Connection, token: str) -> ShareLink | None:
  row = db.execute(
    "SELECT * FROM share_links WHERE token_hash = ?", (_hash(token),)
  ).fetchone()
  return None if row is None else _from_row(row)


def list_for_object(
  db: sqlite3.Connection, object_type: str, object_id: int
) -> list[ShareLink]:
  rows = db.execute(
    "SELECT * FROM share_links WHERE object_type = ? AND object_id = ? ORDER BY id",
    (object_type, object_id),
  )
  return [_from_row(row) for row in rows]


def list_all(db: sqlite3.Connection) -> list[ShareLink]:
  rows = db.execute("SELECT * FROM share_links ORDER BY id")
  return [_from_row(row) for row in rows]


def is_active(link: ShareLink, at: datetime) -> bool:
  """True when a link can still open its record."""
  if link.revoked_at is not None:
    return False
  return link.expires_at is None or link.expires_at > at


def revoke(db: sqlite3.Connection, link_id: int, *, at: datetime) -> ShareLink | None:
  db.execute(
    "UPDATE share_links SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
    (pack_time(at), link_id),
  )
  db.commit()
  return get(db, link_id)


def consume_view(db: sqlite3.Connection, link_id: int, *, at: datetime) -> bool:
  """Claim the one signed-out view. True only for the first claim."""
  cursor = db.execute(
    "UPDATE share_links SET view_consumed_at = ? "
    "WHERE id = ? AND view_consumed_at IS NULL AND revoked_at IS NULL "
    "AND (expires_at IS NULL OR expires_at > ?)",
    (pack_time(at), link_id, pack_time(at)),
  )
  db.commit()
  return cursor.rowcount == 1


def _from_row(row: sqlite3.Row) -> ShareLink:
  return ShareLink(
    id=row["id"],
    object_type=row["object_type"],
    object_id=row["object_id"],
    permissions=tuple(json.loads(row["permissions"])),
    created_by_id=row["created_by_id"],
    created_at=unpack_time(row["created_at"]),
    expires_at=unpack_time(row["expires_at"]),
    revoked_at=unpack_time(row["revoked_at"]),
    view_consumed_at=unpack_time(row["view_consumed_at"]),
  )
