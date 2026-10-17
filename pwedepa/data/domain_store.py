"""Domains as rows the app owns. The config file fills the table once."""

from pathlib import Path

import yaml
from sqlalchemy.exc import IntegrityError

from . import db as data_db
from .domains import Domain, DomainConfigError, parse


def read_all(db_path: str | Path | None = None) -> tuple[Domain, ...]:
  """Return the Domains in the order they joined the list."""
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
  """Return the requests, issues, and announcements a remove would delete."""
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
