"""Save, load, and list Issues in SQLite."""

from dataclasses import replace

from sqlalchemy.engine import Connection, Row

from pwedepa.core import Issue, IssueStatus, Priority, Visibility

from ._rows import pack_domains, pack_time, unpack_domains, unpack_time

COLUMNS = (
  "id, title, description, status, source_request_id, requester_id, "
  "assignee_id, priority, visibility, domains, created_at, updated_at, deleted_at"
)


def save(db: Connection, issue: Issue, *, commit: bool = True) -> Issue:
  """Store the issue. An unsaved issue takes the id SQLite assigns."""
  cursor = db.exec_driver_sql(
    f"INSERT INTO issues ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(id) DO UPDATE SET title = excluded.title, "
    "description = excluded.description, status = excluded.status, "
    "source_request_id = excluded.source_request_id, "
    "requester_id = excluded.requester_id, assignee_id = excluded.assignee_id, "
    "priority = excluded.priority, visibility = excluded.visibility, "
    "domains = excluded.domains, created_at = excluded.created_at, "
    "updated_at = excluded.updated_at, deleted_at = excluded.deleted_at",
    (
      issue.id or None,
      issue.title,
      issue.description,
      issue.status.value,
      issue.source_request_id,
      issue.requester_id,
      issue.assignee_id,
      issue.priority.value,
      issue.visibility.value,
      pack_domains(issue.domains),
      pack_time(issue.created_at),
      pack_time(issue.updated_at),
      pack_time(issue.deleted_at),
    ),
  )
  if commit:
    db.commit()
  return issue if issue.id else replace(issue, id=cursor.lastrowid)


def get(db: Connection, issue_id: int) -> Issue | None:
  row = db.exec_driver_sql("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
  return None if row is None else _from_row(row)


def list_issues(
  db: Connection,
  *,
  status: IssueStatus | None = None,
  requester_id: int | None = None,
  assignee_id: int | None = None,
  domain: str | None = None,
  include_deleted: bool = False,
) -> list[Issue]:
  query = "SELECT * FROM issues"
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
  if assignee_id is not None:
    clauses.append("assignee_id = ?")
    params.append(assignee_id)
  if domain is not None:
    # domains holds a JSON list. json_each matches one exact member.
    clauses.append("EXISTS (SELECT 1 FROM json_each(domains) WHERE value = ?)")
    params.append(domain)
  if clauses:
    query += " WHERE " + " AND ".join(clauses)
  query += " ORDER BY id"
  return [_from_row(row) for row in db.exec_driver_sql(query, tuple(params))]


def _from_row(row: Row) -> Issue:
  return Issue(
    id=row._mapping["id"],
    title=row._mapping["title"],
    description=row._mapping["description"],
    status=IssueStatus(row._mapping["status"]),
    source_request_id=row._mapping["source_request_id"],
    requester_id=row._mapping["requester_id"],
    assignee_id=row._mapping["assignee_id"],
    priority=Priority(row._mapping["priority"]),
    visibility=Visibility(row._mapping["visibility"]),
    domains=unpack_domains(row._mapping["domains"]),
    created_at=unpack_time(row._mapping["created_at"]),
    updated_at=unpack_time(row._mapping["updated_at"]),
    deleted_at=unpack_time(row._mapping["deleted_at"]),
  )
