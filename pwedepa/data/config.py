"""Read the settings a config file carries beside its Domains."""

import os
from pathlib import Path

from . import domains


def read(db_path: str | Path | None = None) -> dict:
  """Return the keys in force: the dev file whole, else config.yml, plus an import."""
  path = domains.active_path(db_path)
  if not path.is_file():
    return {}
  # The dev file is standalone, so it replaces config.yml. An import only adds Domains.
  base = domains.dev_path() if domains.dev_path().is_file() else domains.CONFIG
  settings = domains.mapping(base.read_text(encoding="utf-8")) if base.is_file() else {}
  if path != base:
    settings.update(domains.mapping(path.read_text(encoding="utf-8")))
  return settings


def value(settings: dict, key: str, env: str, default):
  """Return a file key, then its environment variable, then the default."""
  found = settings.get(key)
  if found not in (None, ""):
    return found
  return os.environ.get(env, default)
