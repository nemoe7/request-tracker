"""Insert the records a dev config names, when the database holds none."""

import sys
from datetime import datetime

from pwedepa.core import Issue, IssueStatus, Request, RequestStatus, Visibility

from . import issues as issues_data
from . import requests as requests_data


class SeedError(ValueError):
  """The seed block cannot become records."""


def _status(kind: str, raw: str):
  """Return the status enum for one kind, or raise a message the log can show."""
  if kind == "request":
    try:
      return RequestStatus(raw)
    except ValueError as error:
      raise SeedError(f"a request has no status {raw}") from error
  try:
    return IssueStatus(raw)
  except ValueError as error:
    raise SeedError(f"an issue has no status {raw}") from error


def _add(db, entry: dict, at: datetime) -> None:
  if not isinstance(entry, dict):
    raise SeedError("each seed row needs a kind, a title, a description, and a domain")
  kind = str(entry.get("kind", "request")).lower()
  title = str(entry.get("title", "")).strip()
  description = str(entry.get("description", "")).strip()
  domain = str(entry.get("domain", "")).strip()
  if kind not in ("request", "issue"):
    raise SeedError(f"a seed row has no kind {kind}")
  if not title or not description or not domain:
    raise SeedError("each seed row needs a kind, a title, a description, and a domain")
  status = _status(kind, str(entry.get("status", "OPEN")).upper())
  if kind == "request":
    requests_data.save(
      db,
      Request(
        id=0,
        title=title,
        description=description,
        status=status,
        visibility=Visibility.PUBLIC,
        domains=(domain,),
        created_at=at,
        updated_at=at,
      ),
      commit=False,
    )
    return
  issues_data.save(
    db,
    Issue(
      id=0,
      title=title,
      description=description,
      status=status,
      visibility=Visibility.PUBLIC,
      domains=(domain,),
      created_at=at,
      updated_at=at,
    ),
    commit=False,
  )


def seed(db, entries: list, *, at: datetime) -> int:
  """Insert the rows when both record tables are empty, and say how many."""
  if db.exec_driver_sql("SELECT count(*) FROM requests").scalar_one():
    return 0
  if db.exec_driver_sql("SELECT count(*) FROM issues").scalar_one():
    return 0
  try:
    for entry in entries:
      _add(db, entry, at)
  except BaseException:
    db.rollback()
    raise
  db.commit()
  return len(entries)


def seed_from_config(db_path, settings: dict, *, at: datetime) -> int:
  """Read the seed block and fill an empty database, printing one line."""
  entries = settings.get("seed")
  if not entries:
    return 0
  if not isinstance(entries, list):
    raise SeedError("the seed block needs a list of rows")
  from . import db as data_db

  connection = data_db.connect(db_path)
  try:
    added = seed(connection, entries, at=at)
  finally:
    connection.close()
  if added:
    print(f"Seed: {added} records added.", file=sys.stderr, flush=True)
  return added


__all__ = ["SeedError", "seed", "seed_from_config"]
