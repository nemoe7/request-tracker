"""Domain subscriptions: a person hears about the announcements of a Domain."""

from sqlalchemy.engine import Connection


def subscribed(db: Connection, user_id: int, slug: str) -> bool:
  """True when this person follows the Domain slug."""
  row = db.exec_driver_sql(
    "SELECT 1 FROM domain_subscriptions WHERE user_id = ? AND domain = ?",
    (user_id, slug),
  ).fetchone()
  return row is not None


def set_subscribed(
  db: Connection, user_id: int, slug: str, *, on: bool, commit: bool = True
) -> None:
  """Add or drop one subscription for a Domain slug."""
  if on:
    db.exec_driver_sql(
      "INSERT OR IGNORE INTO domain_subscriptions (user_id, domain) VALUES (?, ?)",
      (user_id, slug),
    )
  else:
    db.exec_driver_sql(
      "DELETE FROM domain_subscriptions WHERE user_id = ? AND domain = ?",
      (user_id, slug),
    )
  if commit:
    db.commit()


def subscribers(db: Connection, slug: str) -> list[int]:
  """Return the ids of the people who follow the Domain slug."""
  rows = db.exec_driver_sql(
    "SELECT user_id FROM domain_subscriptions WHERE domain = ? ORDER BY user_id",
    (slug,),
  ).fetchall()
  return [row._mapping["user_id"] for row in rows]
