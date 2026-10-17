"""A database file carries the schema number this code can open."""

import sqlite3

import pytest

from pwedepa.data import db


def _columns(path, table):
  raw = sqlite3.connect(path)
  try:
    return {row[1] for row in raw.execute(f"PRAGMA table_info({table})")}
  finally:
    raw.close()


def _version(path):
  raw = sqlite3.connect(path)
  try:
    return raw.execute("PRAGMA user_version").fetchone()[0]
  finally:
    raw.close()


def _old_file(path):
  """A 0.1.0 file: the two repaired spots still carry their old shape."""
  raw = sqlite3.connect(path)
  raw.execute("CREATE TABLE user_preferences (user_id INTEGER PRIMARY KEY)")
  raw.execute(
    "CREATE TABLE enrollment_tokens ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "user_id INTEGER NOT NULL, "
    "token_hash TEXT NOT NULL UNIQUE, "
    "created_at TEXT NOT NULL, "
    "expires_at TEXT NOT NULL, "
    "used_at TEXT)"
  )
  raw.commit()
  raw.close()


def test_a_new_file_starts_at_the_current_version(tmp_path):
  path = tmp_path / "new.db"
  db.connect(path).close()

  assert _version(path) == db.SCHEMA_VERSION
  assert "theme" in _columns(path, "user_preferences")
  assert "role" in _columns(path, "enrollment_tokens")


def test_a_version_zero_file_takes_the_repairs_and_moves_up(tmp_path):
  path = tmp_path / "old.db"
  _old_file(path)

  db.connect(path).close()

  assert _version(path) == db.SCHEMA_VERSION
  assert "theme" in _columns(path, "user_preferences")
  assert "role" in _columns(path, "enrollment_tokens")
  assert "user_id" not in _columns(path, "enrollment_tokens")


def test_a_version_one_file_moves_revoked_rows_to_rejected(tmp_path):
  path = tmp_path / "v1.db"
  raw = sqlite3.connect(path)
  for statement in db.SCHEMA.split(";"):
    if statement.strip():
      raw.execute(statement)
  raw.execute(
    "INSERT INTO requests (id, title, description, status, visibility) "
    "VALUES (1, 'Old', '', 'REVOKED', 'PRIVATE')"
  )
  raw.execute(
    "INSERT INTO events (object_type, object_id, event_type, actor_id, at, data) "
    "VALUES ('request', 1, 'request.state_changed', NULL, '2026-01-01T00:00:00+00:00', "
    '\'{"from": "OPEN", "to": "REVOKED"}\')'
  )
  raw.execute("PRAGMA user_version = 1")
  raw.commit()
  raw.close()

  connection = db.connect(path)
  try:
    status = connection.exec_driver_sql(
      "SELECT status FROM requests WHERE id = 1"
    ).scalar_one()
    data = connection.exec_driver_sql(
      "SELECT data FROM events WHERE object_id = 1"
    ).scalar_one()
  finally:
    connection.close()

  assert status == "REJECTED"
  assert "REVOKED" not in data
  assert _version(path) == db.SCHEMA_VERSION


def test_a_file_from_the_future_stops_with_the_path_and_the_reset(tmp_path):
  path = tmp_path / "ahead.db"
  raw = sqlite3.connect(path)
  raw.execute("CREATE TABLE requests (id INTEGER PRIMARY KEY)")
  raw.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
  raw.commit()
  raw.close()

  with pytest.raises(db.SchemaVersionError) as caught:
    db.connect(path)

  message = str(caught.value)
  assert str(path) in message
  assert f"rm {path}" in message
