"""Domain subscriptions: a person hears about the announcements of a Domain."""

from sqlalchemy.engine import Connection


def subscribed(db: Connection, user_id: int, domain: str) -> bool:
  """True when this person follows the Domain."""
  row = db.exec_driver_sql(
    "SELECT 1 FROM domain_subscriptions WHERE user_id = ? AND domain = ?",
    (user_id, domain),
  ).fetchone()
  return row is not None


def set_subscribed(
  db: Connection, user_id: int, domain: str, *, on: bool, commit: bool = True
) -> None:
  """Add or drop one subscription."""
  if on:
    db.exec_driver_sql(
      "INSERT OR IGNORE INTO domain_subscriptions (user_id, domain) VALUES (?, ?)",
      (user_id, domain),
    )
  else:
    db.exec_driver_sql(
      "DELETE FROM domain_subscriptions WHERE user_id = ? AND domain = ?",
      (user_id, domain),
    )
  if commit:
    db.commit()


def subscribers(db: Connection, domain: str) -> list[int]:
  """Return the ids of the people who follow the Domain."""
  rows = db.exec_driver_sql(
    "SELECT user_id FROM domain_subscriptions WHERE domain = ? ORDER BY user_id",
    (domain,),
  ).fetchall()
  return [row._mapping["user_id"] for row in rows]
