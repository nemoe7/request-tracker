from dataclasses import replace

from sqlalchemy.engine import Connection, Row

from pwedepa.core import Priority, Request, RequestStatus, Visibility

from ._rows import pack_domains, pack_time, unpack_domains, unpack_time

COLUMNS = (
  "id, title, description, status, requester_id, priority_suggestion, "
  "priority_unsure, visibility, domains, created_at, updated_at, deleted_at"
)


def save(db: Connection, request: Request, *, commit: bool = True) -> Request:
  """Store the request. An unsaved request takes the id SQLite assigns."""
  cursor = db.exec_driver_sql(
    f"INSERT INTO requests ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET title = excluded.title, "
    "description = excluded.description, status = excluded.status, "
    "requester_id = excluded.requester_id, "
    "priority_suggestion = excluded.priority_suggestion, "
    "priority_unsure = excluded.priority_unsure, visibility = excluded.visibility, "
    "domains = excluded.domains, created_at = excluded.created_at, "
    "updated_at = excluded.updated_at, deleted_at = excluded.deleted_at",
    (
      request.id or None,
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
  if commit:
    db.commit()
  return request if request.id else replace(request, id=cursor.lastrowid)


def get(db: Connection, request_id: int) -> Request | None:
  row = db.exec_driver_sql(
    "SELECT * FROM requests WHERE id = ?", (request_id,)
  ).fetchone()
  return None if row is None else _from_row(row)


def list_requests(
  db: Connection,
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
  return [_from_row(row) for row in db.exec_driver_sql(query, tuple(params))]


def _from_row(row: Row) -> Request:
  return Request(
    id=row._mapping["id"],
    title=row._mapping["title"],
    description=row._mapping["description"],
    status=RequestStatus(row._mapping["status"]),
    requester_id=row._mapping["requester_id"],
    priority_suggestion=(
      None
      if row._mapping["priority_suggestion"] is None
      else Priority(row._mapping["priority_suggestion"])
    ),
    priority_unsure=bool(row._mapping["priority_unsure"]),
    visibility=Visibility(row._mapping["visibility"]),
    domains=unpack_domains(row._mapping["domains"]),
    created_at=unpack_time(row._mapping["created_at"]),
    updated_at=unpack_time(row._mapping["updated_at"]),
    deleted_at=unpack_time(row._mapping["deleted_at"]),
  )
