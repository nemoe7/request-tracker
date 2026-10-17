"""SQLAlchemy storage opening and schema loading for the data layer."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

# The number this code needs. A file carries its own number in PRAGMA
# user_version, and a step in initialize() moves a lower file up one version.
SCHEMA_VERSION = 2

SCHEMA = files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


class SchemaVersionError(RuntimeError):
  pass


_engines: dict[str, Engine] = {}

# A file keeps its schema for the life of the process, so the schema runs once
# per path and not once per request.
_prepared: set[str] = set()


def _key(path: str | Path) -> str:
  return str(Path(path).resolve())


def _engine(path: str | Path) -> Engine:
  key = _key(path)
  if key not in _engines:
    engine = create_engine(f"sqlite:///{key}")

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record) -> None:
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode = WAL")
      cursor.execute("PRAGMA foreign_keys = ON")
      cursor.close()

    _engines[key] = engine
  return _engines[key]


def connect(path: str | Path) -> Connection:
  """Open the database at path, creating its schema when the path is new."""
  key = _key(path)
  connection = _engine(key).connect()
  if key not in _prepared:
    try:
      initialize(connection, key)
    except BaseException:
      connection.close()
      raise
    _prepared.add(key)
  return connection


def _version(db: Connection) -> int:
  return int(db.exec_driver_sql("PRAGMA user_version").scalar_one())


def initialize(db: Connection, path: str | Path | None = None) -> None:
  """Bring the file to the schema this code needs, one version step at a time."""
  found = _version(db)
  if found > SCHEMA_VERSION:
    where = _key(path) if path is not None else "the database"
    raise SchemaVersionError(
      f"{where} is schema version {found}, and this code stops at {SCHEMA_VERSION}. "
      f"Use a newer release, or delete the file and start again: rm {where}"
    )
  for statement in SCHEMA.split(";"):
    if statement.strip():
      db.exec_driver_sql(statement)
  if found < 1:
    _step_one(db)
  if found < 2:
    _step_two(db)
  # A later step reads the number, adds its guard, and moves the number again.
  db.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
  db.commit()


def _step_one(db: Connection) -> None:
  """Give an old file the theme column and a token that names a role."""
  columns = {
    row._mapping["name"]
    for row in db.exec_driver_sql("PRAGMA table_info(user_preferences)")
  }
  if "theme" not in columns:
    db.exec_driver_sql(
      "ALTER TABLE user_preferences ADD COLUMN theme TEXT NOT NULL DEFAULT 'system'"
    )
  tokens = {
    row._mapping["name"]
    for row in db.exec_driver_sql("PRAGMA table_info(enrollment_tokens)")
  }
  if "user_id" in tokens:
    # Old tokens bound a user, so drop them. A token now names a role.
    db.exec_driver_sql("ALTER TABLE enrollment_tokens RENAME TO enrollment_tokens_old")
    db.exec_driver_sql(
      "CREATE TABLE enrollment_tokens ("
      "id INTEGER PRIMARY KEY AUTOINCREMENT, "
      "role TEXT NOT NULL, "
      "token_hash TEXT NOT NULL UNIQUE, "
      "created_at TEXT NOT NULL, "
      "expires_at TEXT NOT NULL, "
      "used_at TEXT)"
    )
    db.exec_driver_sql("DROP TABLE enrollment_tokens_old")


def _step_two(db: Connection) -> None:
  """Reject is the one word for a declined request, so old rows move."""
  db.exec_driver_sql("UPDATE requests SET status = 'REJECTED' WHERE status = 'REVOKED'")
  rows = db.exec_driver_sql(
    "SELECT id, data FROM events WHERE data LIKE '%REVOKED%'"
  ).fetchall()
  for row in rows:
    data = json.loads(row._mapping["data"])
    for key in ("from", "to"):
      if data.get(key) == "REVOKED":
        data[key] = "REJECTED"
    db.exec_driver_sql(
      "UPDATE events SET data = ? WHERE id = ?", (json.dumps(data), row._mapping["id"])
    )


@contextmanager
def transaction(db: Connection) -> Iterator[Connection]:
  try:
    yield db
  except BaseException:
    db.rollback()
    raise
  db.commit()
