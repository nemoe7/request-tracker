"""Per-user display preferences."""

from sqlalchemy.engine import Connection

CLOCKS = ("12", "24")
DEFAULT_CLOCK = "12"


def get_clock(db: Connection, user_id: int) -> str:
  row = db.exec_driver_sql(
    "SELECT clock FROM user_preferences WHERE user_id = ?", (user_id,)
  ).fetchone()
  if row is None:
    return DEFAULT_CLOCK
  return row._mapping["clock"]


def set_clock(db: Connection, user_id: int, clock: str) -> None:
  if clock not in CLOCKS:
    raise ValueError(f"unknown clock format: {clock}")
  db.exec_driver_sql(
    "INSERT INTO user_preferences (user_id, clock) VALUES (?, ?) "
    "ON CONFLICT(user_id) DO UPDATE SET clock = excluded.clock",
    (user_id, clock),
  )
  db.commit()
