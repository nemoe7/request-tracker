from sqlalchemy.engine import Connection

CLOCKS = ("12", "24")
THEMES = ("system", "light", "dark")
DEFAULT_CLOCK = "12"
DEFAULT_THEME = "system"


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


def get_theme(db: Connection, user_id: int) -> str:
  row = db.exec_driver_sql(
    "SELECT theme FROM user_preferences WHERE user_id = ?", (user_id,)
  ).fetchone()
  if row is None:
    return DEFAULT_THEME
  return row._mapping["theme"]


def set_theme(db: Connection, user_id: int, theme: str) -> None:
  if theme not in THEMES:
    raise ValueError(f"unknown theme: {theme}")
  db.exec_driver_sql(
    "INSERT INTO user_preferences (user_id, theme) VALUES (?, ?) "
    "ON CONFLICT(user_id) DO UPDATE SET theme = excluded.theme",
    (user_id, theme),
  )
  db.commit()
