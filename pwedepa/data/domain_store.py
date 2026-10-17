"""Domains as rows the app owns. The config file fills the table once."""

from pathlib import Path

import yaml

from . import db as data_db
from .domains import Domain, parse


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
