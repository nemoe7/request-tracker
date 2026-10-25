"""A reset clears the content and keeps every account."""

from datetime import UTC, datetime

from demo_seed import seed

from pwedepa.data import db
from pwedepa.data.reset import CLEAR, reset

# Tables preserved on reset: people, roles and grants, passkeys,
# settings, sign-up tokens, and account-change audit events.
KEPT = (
  "users",
  "user_roles",
  "permission_grants",
  "passkeys",
  "user_preferences",
  "enrollment_tokens",
  "audit_events",
)


def _count(connection, table):
  return connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()


def test_a_reset_clears_the_records_and_keeps_the_accounts(tmp_path):
  path = tmp_path / "demo.db"
  connection = db.connect(path)
  people = seed(connection, now=datetime.now(UTC), db_path=path)
  admin = people["admin"]
  at = "2026-01-01T00:00:00+00:00"
  connection.exec_driver_sql(
    "INSERT INTO passkeys (user_id, credential_id, public_key, sign_count, created_at) "
    "VALUES (?, ?, ?, ?, ?)",
    (admin.id, b"cred-1", b"key-1", 0, at),
  )
  connection.exec_driver_sql(
    "INSERT INTO sessions (user_id, token_hash, created_at, expires_at) "
    "VALUES (?, ?, ?, ?)",
    (admin.id, "hash-1", at, "2026-02-01T00:00:00+00:00"),
  )
  connection.exec_driver_sql(
    "INSERT INTO audit_events (actor_id, event_type, created_at) VALUES (?, ?, ?)",
    (admin.id, "role.granted", at),
  )
  connection.exec_driver_sql(
    "INSERT INTO enrollment_tokens (role, token_hash, created_at, expires_at) "
    "VALUES (?, ?, ?, ?)",
    ("REQUESTER", "hash-2", at, "2026-02-01T00:00:00+00:00"),
  )
  connection.commit()
  assert _count(connection, "requests") > 0

  kept = {table: _count(connection, table) for table in KEPT}

  reset(connection)

  assert {table: _count(connection, table) for table in KEPT} == kept
  for table in CLEAR:
    assert _count(connection, table) == 0, table
