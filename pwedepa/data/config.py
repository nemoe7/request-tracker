"""Read the settings a config file carries beside its Domains."""

import os
from pathlib import Path

import yaml

from . import domains
from .domains import DomainConfigError


def read(db_path: str | Path | None = None) -> dict:
  """Return the top-level keys of the config in force, or an empty map."""
  path = domains.active_path(db_path)
  if not path.is_file():
    return {}
  try:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
  except yaml.YAMLError as error:
    raise DomainConfigError(f"the YAML does not read: {error}") from error
  return raw if isinstance(raw, dict) else {}


def value(settings: dict, key: str, env: str, default):
  """Return a file key, then its environment variable, then the default."""
  found = settings.get(key)
  if found not in (None, ""):
    return found
  return os.environ.get(env, default)
