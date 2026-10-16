"""SQLite opening and schema for the data layer."""

import sqlite3
from pathlib import Path

# Hard-dev schema: recreate the database instead of migrating it.
SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
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
CREATE TABLE IF NOT EXISTS issues (
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
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_type TEXT NOT NULL,
  object_id INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  actor_id INTEGER,
  at TEXT,
  data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived_at TEXT
);
CREATE TABLE IF NOT EXISTS user_roles (
  user_id INTEGER NOT NULL REFERENCES users(id),
  role TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, role)
);
CREATE TABLE IF NOT EXISTS permission_grants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  permission TEXT NOT NULL,
  effect TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  UNIQUE (user_id, permission, effect)
);
CREATE TABLE IF NOT EXISTS passkeys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  credential_id BLOB NOT NULL UNIQUE,
  public_key BLOB NOT NULL,
  sign_count INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS webauthn_challenges (
  id TEXT PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  ceremony TEXT NOT NULL,
  challenge BLOB NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE TABLE IF NOT EXISTS enrollment_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT,
  replaced_by_id INTEGER REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id INTEGER,
  event_type TEXT NOT NULL,
  object_type TEXT,
  object_id INTEGER,
  data TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS share_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_type TEXT NOT NULL,
  object_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  permissions TEXT NOT NULL DEFAULT '[]',
  created_by_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  expires_at TEXT,
  revoked_at TEXT,
  view_consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  category TEXT NOT NULL,
  object_type TEXT,
  object_id INTEGER,
  message TEXT NOT NULL,
  actor_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_preferences (
  user_id INTEGER NOT NULL REFERENCES users(id),
  category TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  inbox_enabled INTEGER NOT NULL DEFAULT 1,
  pip_enabled INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, category)
);
CREATE TABLE IF NOT EXISTS site_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  created_by_id INTEGER REFERENCES users(id)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
  """Open the database at path, creating its schema when needed."""
  db = sqlite3.connect(path)
  db.row_factory = sqlite3.Row
  db.execute("PRAGMA journal_mode = WAL")
  db.execute("PRAGMA foreign_keys = ON")
  initialize(db)
  return db


def initialize(db: sqlite3.Connection) -> None:
  """Create every table when it is missing."""
  db.executescript(SCHEMA)
  db.commit()
