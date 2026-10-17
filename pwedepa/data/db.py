"""SQLAlchemy storage opening and schema loading for the data layer."""

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

# Hard-dev schema: recreate the database instead of migrating it.
# The project installs Alembic and keeps it ready. The first real
# migration lands only when a schema change must survive existing data.
SCHEMA = files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


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
    initialize(connection)
    _prepared.add(key)
  return connection


def initialize(db: Connection) -> None:
  """Create every table when it is missing, and add a column an older file lacks."""
  for statement in SCHEMA.split(";"):
    if statement.strip():
      db.exec_driver_sql(statement)
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
    # A token now names a role, not a person. Old tokens bound a user, so drop them.
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
  db.commit()


@contextmanager
def transaction(db: Connection) -> Iterator[Connection]:
  """Run every write in one transaction, or leave no write behind."""
  try:
    yield db
  except BaseException:
    db.rollback()
    raise
  db.commit()
