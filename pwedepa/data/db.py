"""SQLite opening and schema migrations for the data layer."""

import sqlite3
from pathlib import Path

# One entry per schema version, in order. Migration N moves user_version N to N+1.
MIGRATIONS = (
  """
  CREATE TABLE requests (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    requester_id INTEGER,
    priority_suggestion TEXT,
    priority_unsure INTEGER NOT NULL DEFAULT 0,
    visibility TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT
  );
  CREATE TABLE issues (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    source_request_id INTEGER,
    requester_id INTEGER,
    assignee_id INTEGER,
    priority TEXT NOT NULL,
    visibility TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',
    created_at TEXT,
    updated_at TEXT,
    deleted_at TEXT
  );
  CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_id INTEGER,
    at TEXT,
    data TEXT NOT NULL DEFAULT '{}'
  );
  """,
)


def connect(path: str | Path) -> sqlite3.Connection:
  """Open the database at path, creating and migrating it when needed."""
  db = sqlite3.connect(path)
  db.row_factory = sqlite3.Row
  db.execute("PRAGMA journal_mode = WAL")
  db.execute("PRAGMA foreign_keys = ON")
  migrate(db)
  return db


def migrate(db: sqlite3.Connection) -> None:
  """Apply every pending migration once, tracked by PRAGMA user_version."""
  version = db.execute("PRAGMA user_version").fetchone()[0]
  for step in MIGRATIONS[version:]:
    db.executescript(step)
    version += 1
    db.execute(f"PRAGMA user_version = {version}")
  db.commit()
