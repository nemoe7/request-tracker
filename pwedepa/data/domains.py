"""The Domains config: YAML names, URL slugs, and descriptions."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "domains.yaml"
MOUNTED_ENV = "PWEDEPA_DOMAINS_CONFIG"
IMPORTED_NAME = "domains.imported.yaml"


class DomainConfigError(ValueError):
  """The config file cannot become a list of Domains."""


@dataclass(frozen=True)
class Domain:
  name: str
  slug: str
  description: str = ""


def slugify(name: str) -> str:
  """Return the URL segment for one Domain name."""
  return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _db_path(db_path: str | Path | None) -> Path:
  raw = db_path or os.environ.get("PWEDEPA_DB", "pwedepa.db")
  return Path(raw).resolve()


def imported_path(db_path: str | Path | None = None) -> Path:
  """Return the copy an import writes, beside the database."""
  return _db_path(db_path).parent / IMPORTED_NAME


def mounted_path() -> Path | None:
  """Return the config the operator mounts, when the operator sets one."""
  raw = os.environ.get(MOUNTED_ENV)
  return Path(raw) if raw else None


def active_path(db_path: str | Path | None = None) -> Path:
  """Return the file in force: an import, then the mount, then the package."""
  imported = imported_path(db_path)
  if imported.is_file():
    return imported
  mounted = mounted_path()
  if mounted is not None and mounted.is_file():
    return mounted
  return CONFIG


def parse(text: str) -> tuple[Domain, ...]:
  """Read YAML text into Domains, or raise a message the page can show."""
  try:
    raw = yaml.safe_load(text)
  except yaml.YAMLError as error:
    raise DomainConfigError(f"the YAML does not read: {error}") from error
  if not isinstance(raw, dict) or not isinstance(raw.get("domains"), list):
    raise DomainConfigError("the file needs a domains list")
  found: list[Domain] = []
  seen: dict[str, str] = {}
  for entry in raw["domains"]:
    if not isinstance(entry, dict):
      raise DomainConfigError("each Domain needs a name")
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
      raise DomainConfigError("each Domain needs a name")
    name = name.strip()
    description = entry.get("description", "")
    if not isinstance(description, str):
      raise DomainConfigError(f"{name}: the description must be text")
    slug = slugify(name)
    if not slug:
      raise DomainConfigError(f"{name}: the name makes no URL slug")
    if slug in seen:
      raise DomainConfigError(f"{name}: the slug {slug} is also used by {seen[slug]}")
    seen[slug] = name
    found.append(Domain(name, slug, description.strip()))
  if not found:
    raise DomainConfigError("the file lists no Domain; the demo seeds from these names")
  return tuple(found)


def load(db_path: str | Path | None = None) -> tuple[Domain, ...]:
  """Return the Domains from the file in force."""
  path = active_path(db_path)
  if not path.is_file():
    raise FileNotFoundError(
      f"domains.yaml is missing: looked at {CONFIG} and {imported_path(db_path)}"
    )
  return parse(path.read_text(encoding="utf-8"))


def render(found: tuple[Domain, ...]) -> str:
  """Return canonical YAML for one imported set."""
  return yaml.safe_dump(
    {
      "domains": [
        {"name": domain.name, "description": domain.description} for domain in found
      ]
    },
    allow_unicode=True,
    sort_keys=False,
  )


def import_bytes(raw: bytes, db_path: str | Path | None = None) -> tuple[Domain, ...]:
  """Validate the bytes, then write the copy the app reads on the next call."""
  try:
    text = raw.decode("utf-8")
  except UnicodeDecodeError as error:
    raise DomainConfigError("the file is not UTF-8 text") from error
  found = parse(text)
  path = imported_path(db_path)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(render(found), encoding="utf-8")
  return found


def starter_domains(db_path: str | Path | None = None) -> tuple[str, ...]:
  """Return the configured Domain names, in name order."""
  return tuple(domain.name for domain in load(db_path))


def find(slug: str, db_path: str | Path | None = None) -> Domain | None:
  """Return the Domain for one URL segment, or None."""
  for domain in load(db_path):
    if domain.slug == slug:
      return domain
  return None


def domain_slot(names: tuple[str, ...], index: int) -> str:
  """Return the Domain for a fixed demo slot, and wrap a shorter config."""
  if not names:
    raise ValueError("the Domain config lists no name")
  return names[index % len(names)]
