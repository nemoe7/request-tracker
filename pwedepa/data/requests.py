"""Save, load, and list Requests in SQLite."""

import sqlite3

from pwedepa.core import Priority, Request, RequestStatus, Visibility

from ._rows import pack_domains, pack_time, unpack_domains, unpack_time

COLUMNS = (
  "id, title, description, status, requester_id, priority_suggestion, "
  "priority_unsure, visibility, domains, created_at, updated_at, deleted_at"
)


def save(db: sqlite3.Connection, request: Request) -> None:
  db.execute(
    f"INSERT INTO requests ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET title = excluded.title, "
    "description = excluded.description, status = excluded.status, "
    "requester_id = excluded.requester_id, "
    "priority_suggestion = excluded.priority_suggestion, "
    "priority_unsure = excluded.priority_unsure, visibility = excluded.visibility, "
    "domains = excluded.domains, created_at = excluded.created_at, "
    "updated_at = excluded.updated_at, deleted_at = excluded.deleted_at",
    (
      request.id,
      request.title,
      request.description,
      request.status.value,
      request.requester_id,
      None
      if request.priority_suggestion is None
      else request.priority_suggestion.value,
      int(request.priority_unsure),
      request.visibility.value,
      pack_domains(request.domains),
      pack_time(request.created_at),
      pack_time(request.updated_at),
      pack_time(request.deleted_at),
    ),
  )
  db.commit()


def get(db: sqlite3.Connection, request_id: int) -> Request | None:
  row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
  return None if row is None else _from_row(row)


def list_requests(
  db: sqlite3.Connection,
  *,
  status: RequestStatus | None = None,
  requester_id: int | None = None,
  domain: str | None = None,
  include_deleted: bool = False,
) -> list[Request]:
  query = "SELECT * FROM requests"
  clauses = []
  params: list = []
  if not include_deleted:
    clauses.append("deleted_at IS NULL")
  if status is not None:
    clauses.append("status = ?")
    params.append(status.value)
  if requester_id is not None:
    clauses.append("requester_id = ?")
    params.append(requester_id)
  if domain is not None:
    # domains holds a JSON list. json_each matches one exact member.
    clauses.append("EXISTS (SELECT 1 FROM json_each(domains) WHERE value = ?)")
    params.append(domain)
  if clauses:
    query += " WHERE " + " AND ".join(clauses)
  query += " ORDER BY id"
  return [_from_row(row) for row in db.execute(query, params)]


def _from_row(row: sqlite3.Row) -> Request:
  return Request(
    id=row["id"],
    title=row["title"],
    description=row["description"],
    status=RequestStatus(row["status"]),
    requester_id=row["requester_id"],
    priority_suggestion=(
      None
      if row["priority_suggestion"] is None
      else Priority(row["priority_suggestion"])
    ),
    priority_unsure=bool(row["priority_unsure"]),
    visibility=Visibility(row["visibility"]),
    domains=unpack_domains(row["domains"]),
    created_at=unpack_time(row["created_at"]),
    updated_at=unpack_time(row["updated_at"]),
    deleted_at=unpack_time(row["deleted_at"]),
  )
