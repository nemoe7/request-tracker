"""Share links for Requests and Issues. The database stores token hashes."""

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Connection, Row

from pwedepa._tokens import hash_token, new_token

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


def create(
  db: Connection,
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
  token = new_token()
  cursor = db.exec_driver_sql(
    "INSERT INTO share_links (object_type, object_id, token_hash, permissions, "
    "created_by_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (
      object_type,
      object_id,
      hash_token(token),
      json.dumps(list(ordered)),
      created_by_id,
      pack_time(at),
      pack_time(expires_at),
    ),
  )
  db.commit()
  return IssuedShareLink(get(db, cursor.lastrowid), token)


def get(db: Connection, link_id: int) -> ShareLink | None:
  row = db.exec_driver_sql(
    "SELECT * FROM share_links WHERE id = ?", (link_id,)
  ).fetchone()
  return None if row is None else _from_row(row)


def find_by_token(db: Connection, token: str) -> ShareLink | None:
  row = db.exec_driver_sql(
    "SELECT * FROM share_links WHERE token_hash = ?", (hash_token(token),)
  ).fetchone()
  return None if row is None else _from_row(row)


def list_for_object(
  db: Connection, object_type: str, object_id: int
) -> list[ShareLink]:
  rows = db.exec_driver_sql(
    "SELECT * FROM share_links WHERE object_type = ? AND object_id = ? ORDER BY id",
    (object_type, object_id),
  )
  return [_from_row(row) for row in rows]


def list_all(db: Connection) -> list[ShareLink]:
  rows = db.exec_driver_sql("SELECT * FROM share_links ORDER BY id")
  return [_from_row(row) for row in rows]


def is_active(link: ShareLink, at: datetime) -> bool:
  """True when a link can still open its record."""
  if link.revoked_at is not None:
    return False
  return link.expires_at is None or link.expires_at > at


def revoke(db: Connection, link_id: int, *, at: datetime) -> ShareLink | None:
  db.exec_driver_sql(
    "UPDATE share_links SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
    (pack_time(at), link_id),
  )
  db.commit()
  return get(db, link_id)


def consume_view(db: Connection, link_id: int, *, at: datetime) -> bool:
  """Claim the one signed-out view. True only for the first claim."""
  cursor = db.exec_driver_sql(
    "UPDATE share_links SET view_consumed_at = ? "
    "WHERE id = ? AND view_consumed_at IS NULL AND revoked_at IS NULL "
    "AND (expires_at IS NULL OR expires_at > ?)",
    (pack_time(at), link_id, pack_time(at)),
  )
  db.commit()
  return cursor.rowcount == 1


def _from_row(row: Row) -> ShareLink:
  return ShareLink(
    id=row._mapping["id"],
    object_type=row._mapping["object_type"],
    object_id=row._mapping["object_id"],
    permissions=tuple(json.loads(row._mapping["permissions"])),
    created_by_id=row._mapping["created_by_id"],
    created_at=unpack_time(row._mapping["created_at"]),
    expires_at=unpack_time(row._mapping["expires_at"]),
    revoked_at=unpack_time(row._mapping["revoked_at"]),
    view_consumed_at=unpack_time(row._mapping["view_consumed_at"]),
  )
