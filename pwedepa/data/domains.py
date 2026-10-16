"""The starter Domains, read from the json config at the project root."""

import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "domains.json"
if not CONFIG.is_file():  # an installed package reads the config at the run root
  CONFIG = Path("domains.json")


def starter_domains() -> tuple[str, ...]:
  """Return the configured Domain names, in name order."""
  return tuple(json.loads(CONFIG.read_text(encoding="utf-8")))
