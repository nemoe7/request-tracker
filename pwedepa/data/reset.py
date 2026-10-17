"""Clear the records and keep the accounts, for a development reset."""

from sqlalchemy.engine import Connection

from .db import transaction

# Content that a reset drops. The accounts, their roles and grants, their
# passkeys, their settings, and the account audit trail all stay. A person
# signs in again without a new sign-up.
CLEAR = (
  "issues",
  "requests",
  "events",
  "workspace_reads",
  "notifications",
  "site_messages",
  "announcements",
  "domain_subscriptions",
  "share_links",
  "webauthn_challenges",
  "sessions",
)


def reset(db: Connection) -> dict[str, int]:
  """Delete every record, notice, and session. Keep the accounts."""
  counts: dict[str, int] = {}
  with transaction(db):
    # A session names the one that replaced it, so drop those links first.
    db.exec_driver_sql("UPDATE sessions SET replaced_by_id = NULL")
    for table in CLEAR:
      result = db.exec_driver_sql(f"DELETE FROM {table}")
      counts[table] = result.rowcount or 0
  return counts
