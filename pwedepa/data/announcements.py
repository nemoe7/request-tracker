"""Announcements, one list for each Domain. The Domain slug is the key."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Connection, Row

from ._rows import pack_time, unpack_time


@dataclass(frozen=True)
class Announcement:
  id: int
  slug: str
  title: str
  body: str
  author_id: int
  published_at: datetime | None
  edited_at: datetime | None


def _from_row(row: Row) -> Announcement:
  return Announcement(
    id=row._mapping["id"],
    slug=row._mapping["domain"],
    title=row._mapping["title"],
    body=row._mapping["body"],
    author_id=row._mapping["author_id"],
    published_at=unpack_time(row._mapping["published_at"]),
    edited_at=unpack_time(row._mapping["edited_at"]),
  )


def create(
  db: Connection,
  *,
  slug: str,
  title: str,
  body: str,
  author_id: int,
  at: datetime,
  commit: bool = True,
) -> Announcement:
  """Store one announcement and hand it back."""
  cursor = db.exec_driver_sql(
    "INSERT INTO announcements (domain, title, body, author_id, published_at) "
    "VALUES (?, ?, ?, ?, ?)",
    (slug, title, body, author_id, pack_time(at)),
  )
  if commit:
    db.commit()
  found = get(db, cursor.lastrowid)
  assert found is not None
  return found


def update(
  db: Connection,
  announcement_id: int,
  *,
  title: str,
  body: str,
  at: datetime,
  commit: bool = True,
) -> None:
  """Replace the text of one announcement and mark when it changed."""
  db.exec_driver_sql(
    "UPDATE announcements SET title = ?, body = ?, edited_at = ? WHERE id = ?",
    (title, body, pack_time(at), announcement_id),
  )
  if commit:
    db.commit()


def delete(db: Connection, announcement_id: int, *, commit: bool = True) -> None:
  """Remove one announcement for good."""
  db.exec_driver_sql("DELETE FROM announcements WHERE id = ?", (announcement_id,))
  if commit:
    db.commit()


def get(db: Connection, announcement_id: int) -> Announcement | None:
  row = db.exec_driver_sql(
    "SELECT * FROM announcements WHERE id = ?", (announcement_id,)
  ).fetchone()
  return _from_row(row) if row is not None else None


def list_for_slug(db: Connection, slug: str) -> list[Announcement]:
  """Return the Domain's announcements, newest first."""
  rows = db.exec_driver_sql(
    "SELECT * FROM announcements WHERE domain = ? ORDER BY published_at DESC, id DESC",
    (slug,),
  ).fetchall()
  return [_from_row(row) for row in rows]
