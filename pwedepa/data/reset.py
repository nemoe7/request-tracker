"""Clear requests, issues, and related activity while keeping user accounts."""

from sqlalchemy.engine import Connection

from .db import transaction

# A reset drops the work. Accounts, roles, grants, passkeys, settings, and the
# account audit trail stay, so a person signs in again without a new sign-up.
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
  counts: dict[str, int] = {}
  with transaction(db):
    # A session names the one that replaced it, so drop those links first.
    db.exec_driver_sql("UPDATE sessions SET replaced_by_id = NULL")
    for table in CLEAR:
      result = db.exec_driver_sql(f"DELETE FROM {table}")
      counts[table] = result.rowcount or 0
  return counts
