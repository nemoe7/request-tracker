"""Domains stored as app-owned rows. Config files seed this table once."""

import json
from pathlib import Path

import yaml
from sqlalchemy.exc import IntegrityError

from . import db as data_db
from .domains import Domain, DomainConfigError, parse


def read_all(db_path: str | Path | None = None) -> tuple[Domain, ...]:
  """Return Domains in insertion order."""
  connection = data_db.connect(db_path)
  try:
    rows = connection.exec_driver_sql(
      "SELECT name, slug, description FROM domains ORDER BY id"
    ).all()
  finally:
    connection.close()
  return tuple(Domain(row[0], row[1], row[2]) for row in rows)


def seed_from_file(db_path: str | Path | None, settings: dict) -> int:
  """Fill an empty table from the config list, and change nothing after that."""
  connection = data_db.connect(db_path)
  try:
    if connection.exec_driver_sql("SELECT count(*) FROM domains").scalar_one():
      return 0
    listed = settings.get("domains")
    if not isinstance(listed, list) or not listed:
      return 0
    found = parse(yaml.safe_dump({"domains": listed}))
    for domain in found:
      connection.exec_driver_sql(
        "INSERT INTO domains (name, slug, description) VALUES (?, ?, ?)",
        (domain.name, domain.slug, domain.description),
      )
    connection.commit()
  finally:
    connection.close()
  return len(found)


def add(db_path: str | Path | None, name: str, description: str = "") -> Domain:
  """Add one Domain, with the same checks the file import runs."""
  found = parse(
    yaml.safe_dump({"domains": [{"name": name, "description": description}]})
  )
  domain = found[0]
  connection = data_db.connect(db_path)
  try:
    connection.exec_driver_sql(
      "INSERT INTO domains (name, slug, description) VALUES (?, ?, ?)",
      (domain.name, domain.slug, domain.description),
    )
    connection.commit()
  except IntegrityError as error:
    raise DomainConfigError(f"{domain.name}: the name or slug is taken") from error
  finally:
    connection.close()
  return domain


def _named(db_path, slug: str):
  for domain in read_all(db_path):
    if domain.slug == slug:
      return domain
  return None


def _count(connection, table: str, name: str) -> int:
  return connection.exec_driver_sql(
    f"SELECT count(*) FROM {table} "
    f"WHERE EXISTS (SELECT 1 FROM json_each({table}.domains) WHERE value = ?)",
    (name,),
  ).scalar_one()


def count_records(db_path, slug: str) -> tuple[int, int, int]:
  """Return the requests, issues, and announcements a remove would drop."""
  domain = _named(db_path, slug)
  if domain is None:
    return (0, 0, 0)
  connection = data_db.connect(db_path)
  try:
    requests = _count(connection, "requests", domain.name)
    issues = _count(connection, "issues", domain.name)
    announcements = connection.exec_driver_sql(
      "SELECT count(*) FROM announcements WHERE domain = ?", (slug,)
    ).scalar_one()
  finally:
    connection.close()
  return (requests, issues, announcements)


def remove(db_path, slug: str) -> tuple[int, int, int]:
  """Drop the Domain and every record that names it."""
  domain = _named(db_path, slug)
  if domain is None:
    raise DomainConfigError(f"{slug}: no such Domain")
  connection = data_db.connect(db_path)
  try:
    requests = connection.exec_driver_sql(
      "DELETE FROM requests "
      "WHERE EXISTS (SELECT 1 FROM json_each(requests.domains) WHERE value = ?)",
      (domain.name,),
    ).rowcount
    issues = connection.exec_driver_sql(
      "DELETE FROM issues "
      "WHERE EXISTS (SELECT 1 FROM json_each(issues.domains) WHERE value = ?)",
      (domain.name,),
    ).rowcount
    announcements = connection.exec_driver_sql(
      "DELETE FROM announcements WHERE domain = ?", (slug,)
    ).rowcount
    connection.exec_driver_sql(
      "DELETE FROM domain_subscriptions WHERE domain = ?", (slug,)
    )
    connection.exec_driver_sql("DELETE FROM domains WHERE slug = ?", (slug,))
    connection.commit()
  finally:
    connection.close()
  return (requests, issues, announcements)


def redirect_for(db_path, old_slug: str) -> str | None:
  """Return the slug that holds an old URL, or None."""
  connection = data_db.connect(db_path)
  try:
    row = connection.exec_driver_sql(
      "SELECT slug FROM domain_redirects WHERE old_slug = ?", (old_slug,)
    ).first()
  finally:
    connection.close()
  return row[0] if row else None


def _rewrite_records(connection, table: str, old: str, new: str) -> None:
  rows = connection.exec_driver_sql(f"SELECT id, domains FROM {table}").all()
  for row in rows:
    names = json.loads(row[1])
    if old not in names:
      continue
    connection.exec_driver_sql(
      f"UPDATE {table} SET domains = ? WHERE id = ?",
      (json.dumps([new if name == old else name for name in names]), row[0]),
    )


def rename(db_path, slug: str, *, name: str = "", new_slug: str = "") -> Domain:
  """Rewrite a Domain, keep its records, and hold the old URL on a redirect."""
  current = _named(db_path, slug)
  if current is None:
    raise DomainConfigError(f"{slug}: no such Domain")
  entry = {
    "name": (name or current.name).strip(),
    "slug": (new_slug or current.slug).strip(),
    "description": current.description,
  }
  found = parse(yaml.safe_dump({"domains": [entry]}))[0]
  connection = data_db.connect(db_path)
  try:
    if found.name != current.name:
      _rewrite_records(connection, "requests", current.name, found.name)
      _rewrite_records(connection, "issues", current.name, found.name)
    if found.slug != current.slug:
      connection.exec_driver_sql(
        "UPDATE announcements SET domain = ? WHERE domain = ?", (found.slug, slug)
      )
      connection.exec_driver_sql(
        "UPDATE domain_subscriptions SET domain = ? WHERE domain = ?",
        (found.slug, slug),
      )
      connection.exec_driver_sql(
        "DELETE FROM domain_redirects WHERE old_slug = ?", (found.slug,)
      )
      connection.exec_driver_sql(
        "INSERT OR REPLACE INTO domain_redirects (old_slug, slug) VALUES (?, ?)",
        (slug, found.slug),
      )
    connection.exec_driver_sql(
      "UPDATE domains SET name = ?, slug = ?, description = ? WHERE slug = ?",
      (found.name, found.slug, found.description, slug),
    )
    connection.commit()
  except IntegrityError as error:
    connection.rollback()
    raise DomainConfigError(f"{found.name}: the name or slug is taken") from error
  finally:
    connection.close()
  return found
