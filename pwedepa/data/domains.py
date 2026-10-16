"""The starter Domains, read from the json config at the project root."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "domains.json"
FALLBACK = Path("domains.json")
if not CONFIG.is_file():  # an installed package reads the config at the run root
  CONFIG = FALLBACK


def starter_domains() -> tuple[str, ...]:
  """Return the configured Domain names, in name order."""
  if not CONFIG.is_file():
    raise FileNotFoundError(
      f"domains.json is missing: looked at {ROOT / 'domains.json'} and {FALLBACK.resolve()}"
    )
  names = tuple(json.loads(CONFIG.read_text(encoding="utf-8")))
  if not names:
    raise ValueError(f"{CONFIG} lists no Domain; the demo seeds from these names")
  return names


def domain_slot(names: tuple[str, ...], index: int) -> str:
  """Return the Domain for a fixed demo slot, and wrap a shorter config."""
  if not names:
    raise ValueError("the Domain config lists no name")
  return names[index % len(names)]
