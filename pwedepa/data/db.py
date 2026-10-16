"""SQLAlchemy storage opening and schema loading for the data layer."""

from importlib.resources import files
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine

# Hard-dev schema: recreate the database instead of migrating it.
# The project installs Alembic and keeps it ready. The first real
# migration lands only when a schema change must survive existing data.
SCHEMA = files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


_engines: dict[str, Engine] = {}


def _engine(path: str | Path) -> Engine:
  key = str(Path(path).resolve())
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
  """Open the database at path, creating its schema when needed."""
  connection = _engine(path).connect()
  initialize(connection)
  return connection


def initialize(db: Connection) -> None:
  """Create every table when it is missing."""
  for statement in SCHEMA.split(";"):
    if statement.strip():
      db.exec_driver_sql(statement)
  db.commit()
