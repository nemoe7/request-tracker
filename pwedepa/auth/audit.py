"""The separate security and administration audit trail."""

import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.engine import Connection

from pwedepa.data._rows import pack_time, unpack_time


@dataclass(frozen=True)
class AuditEvent:
  id: int
  actor_id: int | None
  event_type: str
  object_type: str | None
  object_id: int | None
  data: dict = field(default_factory=dict)
  created_at: datetime | None = None


def record_audit(
  db: Connection,
  event_type: str,
  *,
  at: datetime,
  actor_id: int | None = None,
  object_type: str | None = None,
  object_id: int | None = None,
  data: dict | None = None,
  commit: bool = True,
) -> AuditEvent:
  cursor = db.exec_driver_sql(
    "INSERT INTO audit_events "
    "(actor_id, event_type, object_type, object_id, data, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)",
    (
      actor_id,
      event_type,
      object_type,
      object_id,
      json.dumps(data or {}),
      pack_time(at),
    ),
  )
  if commit:
    db.commit()
  return AuditEvent(
    id=cursor.lastrowid,
    actor_id=actor_id,
    event_type=event_type,
    object_type=object_type,
    object_id=object_id,
    data=data or {},
    created_at=at,
  )


def list_audit_events(
  db: Connection,
  *,
  object_type: str | None = None,
  object_id: int | None = None,
  limit: int | None = None,
) -> list[AuditEvent]:
  """Oldest first. A limit keeps the newest of them."""
  query = "SELECT * FROM audit_events"
  clauses = []
  params: list = []
  if object_type is not None:
    clauses.append("object_type = ?")
    params.append(object_type)
  if object_id is not None:
    clauses.append("object_id = ?")
    params.append(object_id)
  if clauses:
    query += " WHERE " + " AND ".join(clauses)
  if limit is None:
    query += " ORDER BY id"
  else:
    # Tail rows live at high IDs, so read descending first.
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
  rows = list(db.exec_driver_sql(query, tuple(params)))
  if limit is not None:
    rows.reverse()
  return [
    AuditEvent(
      id=row._mapping["id"],
      actor_id=row._mapping["actor_id"],
      event_type=row._mapping["event_type"],
      object_type=row._mapping["object_type"],
      object_id=row._mapping["object_id"],
      data=json.loads(row._mapping["data"]),
      created_at=unpack_time(row._mapping["created_at"]),
    )
    for row in rows
  ]
