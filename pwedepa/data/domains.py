"""The starter Domains, read from the json config beside the schema."""

import json
from pathlib import Path

CONFIG = Path(__file__).with_name("domains.json")


def starter_domains() -> tuple[str, ...]:
  """Return the configured Domain names, in name order."""
  return tuple(json.loads(CONFIG.read_text(encoding="utf-8")))
