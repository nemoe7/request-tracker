"""Shared value conversions between core objects and SQLite rows."""

import json
from datetime import datetime


def pack_time(value: datetime | None) -> str | None:
  return None if value is None else value.isoformat()


def unpack_time(value: str | None) -> datetime | None:
  return None if value is None else datetime.fromisoformat(value)


def pack_domains(domains: tuple[str, ...]) -> str:
  return json.dumps(list(domains))


def unpack_domains(value: str) -> tuple[str, ...]:
  return tuple(json.loads(value))
