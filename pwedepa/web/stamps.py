"""Timestamp rendering: relative under 72 hours, absolute after."""

from datetime import datetime, timedelta

RELATIVE_LIMIT = timedelta(hours=72)


def format_stamp(value: datetime | None, clock: str, at: datetime) -> str:
  if value is None:
    return ""
  delta = at - value
  if delta < timedelta(minutes=1):
    return "just now"
  if delta < timedelta(hours=1):
    return f"{int(delta.total_seconds() // 60)}m ago"
  if delta < timedelta(hours=24):
    return f"{int(delta.total_seconds() // 3600)}h ago"
  if delta < RELATIVE_LIMIT:
    return f"{delta.days}d ago"
  if clock == "24":
    return value.strftime("%b %-d, %H:%M")
  return value.strftime("%b %-d, %-I:%M %p")
