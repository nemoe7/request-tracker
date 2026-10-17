"""Read the settings a config file carries beside its Domains."""

import os
from pathlib import Path

from . import domains


def read(db_path: str | Path | None = None) -> dict:
  """Return the keys in force: config.yml, then the file that wins over it."""
  base = domains.CONFIG
  settings = domains.mapping(base.read_text(encoding="utf-8")) if base.is_file() else {}
  path = domains.active_path(db_path)
  if path != base and path.is_file():
    settings.update(domains.mapping(path.read_text(encoding="utf-8")))
  return settings


def value(settings: dict, key: str, env: str, default):
  """Return a file key, then its environment variable, then the default."""
  found = settings.get(key)
  if found not in (None, ""):
    return found
  return os.environ.get(env, default)
