"""Insert the rows a dev config names, when the database holds none."""

import sys
from datetime import datetime
from itertools import cycle

from pwedepa.core import Issue, IssueStatus, Request, RequestStatus, Visibility

from . import issues as issues_data
from . import requests as requests_data


class SeedError(ValueError):
  pass


# Seed rows need an owner, and accounts come from the auth layer. The import
# waits inside the function so the data package loads on its own.
PEOPLE = (
  ("seed-ari", "Ari Cruz"),
  ("seed-bea", "Bea Lim"),
  ("seed-carlo", "Carlo Reyes"),
)


def _requesters(db, *, at: datetime) -> list[int]:
  """Create the demo requesters once, and return their ids."""
  from pwedepa.auth import Role, assign_role, users

  ids = []
  for username, display_name in PEOPLE:
    person = users.get_user_by_username(db, username)
    if person is None:
      person = users.create_user(db, username, display_name, at=at)
    assign_role(db, person.id, Role.REQUESTER, at=at)
    ids.append(person.id)
  return ids


def _status_enum(kind: str, raw: str):
  if kind == "request":
    try:
      return RequestStatus(raw)
    except ValueError as error:
      raise SeedError(f"a request has no status {raw}") from error
  try:
    return IssueStatus(raw)
  except ValueError as error:
    raise SeedError(f"an issue has no status {raw}") from error


def _known_domains(settings: dict) -> set[str]:
  listed = settings.get("domains") or []
  if not isinstance(listed, list):
    raise SeedError("the domains block needs a list")
  return {
    str(entry["name"]).strip()
    for entry in listed
    if isinstance(entry, dict) and entry.get("name")
  }


def _check_domains(entries: list, settings: dict) -> None:
  names = _known_domains(settings)
  if not names:
    return
  for entry in entries:
    if not isinstance(entry, dict):
      continue
    domain = str(entry.get("domain", "")).strip()
    if domain and domain not in names:
      raise SeedError(f"a seed row names no Domain {domain}")


def _count_phrase(entries: list) -> str:
  requests = sum(
    1 for entry in entries if str(entry.get("kind", "request")).lower() == "request"
  )
  issues = len(entries) - requests
  parts = []
  if requests:
    parts.append(f"{requests} request" if requests == 1 else f"{requests} requests")
  if issues:
    parts.append(f"{issues} issue" if issues == 1 else f"{issues} issues")
  return " and ".join(parts)


def _add(db, entry: dict, at: datetime, *, requester_id: int | None = None) -> None:
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
  status = _status_enum(kind, str(entry.get("status", "OPEN")).upper())
  if kind == "request":
    requests_data.save(
      db,
      Request(
        id=0,
        title=title,
        description=description,
        requester_id=requester_id,
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
  """Only when the requests and issues tables are both empty."""
  if db.exec_driver_sql("SELECT count(*) FROM requests").scalar_one():
    return 0
  if db.exec_driver_sql("SELECT count(*) FROM issues").scalar_one():
    return 0
  owners = cycle(_requesters(db, at=at))
  try:
    for entry in entries:
      owner = None
      if str(entry.get("kind", "request")).lower() == "request":
        owner = next(owners)
      _add(db, entry, at, requester_id=owner)
  except BaseException:
    db.rollback()
    raise
  db.commit()
  return len(entries)


def seed_from_config(db_path, settings: dict, *, at: datetime) -> int:
  entries = settings.get("seed")
  if not entries:
    return 0
  if not isinstance(entries, list):
    raise SeedError("the seed block needs a list of rows")
  _check_domains(entries, settings)
  from . import db as data_db

  connection = data_db.connect(db_path)
  try:
    added = seed(connection, entries, at=at)
  finally:
    connection.close()
  if added:
    print(f"Seed: {_count_phrase(entries)} added.", file=sys.stderr, flush=True)
  return added


__all__ = ["SeedError", "seed", "seed_from_config"]
