"""The config file: YAML Domains with names, URL slugs, and descriptions."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config.yml"
IMPORTED_NAME = "domains.imported.yaml"
# The overlay a checkout carries. The released image ships no such file.
DEV_NAME = "config.dev.yml"


_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class DomainConfigError(ValueError):
  pass


@dataclass(frozen=True)
class Domain:
  name: str
  slug: str
  description: str = ""


def slugify(name: str) -> str:
  return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _db_path(db_path: str | Path | None) -> Path:
  raw = db_path or os.environ.get("PWEDEPA_DB", "pwedepa.db")
  return Path(raw).resolve()


def imported_path(db_path: str | Path | None = None) -> Path:
  """Return the copy an import writes, beside the database."""
  return _db_path(db_path).parent / IMPORTED_NAME


def dev_path() -> Path:
  """Return the overlay beside config.yml, when a checkout carries one."""
  return CONFIG.with_name(DEV_NAME)


def active_path(db_path: str | Path | None = None) -> Path:
  """Return the file in force: an import, the dev overlay, else config.yml."""
  imported = imported_path(db_path)
  if imported.is_file():
    return imported
  overlay = dev_path()
  if overlay.is_file():
    return overlay
  return CONFIG


def mapping(text: str) -> dict:
  try:
    raw = yaml.safe_load(text)
  except yaml.YAMLError as error:
    raise DomainConfigError(f"the YAML does not read: {error}") from error
  return raw if isinstance(raw, dict) else {}


def parse(text: str) -> tuple[Domain, ...]:
  """Read YAML text into Domains, or raise a message the page can show."""
  raw = mapping(text)
  if not isinstance(raw.get("domains"), list):
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
    pinned = entry.get("slug")
    if pinned is None:
      slug = slugify(name)
    elif not isinstance(pinned, str) or not _SLUG.fullmatch(pinned.strip()):
      raise DomainConfigError(
        f"{name}: the slug uses lowercase letters, digits, and single dashes"
      )
    else:
      slug = pinned.strip()
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
  path = active_path(db_path)
  if not path.is_file():
    raise FileNotFoundError(
      f"config.yml is missing: looked at {CONFIG} and {imported_path(db_path)}"
    )
  text = path.read_text(encoding="utf-8")
  # A file without the list leaves the Domains to config.yml.
  if path != CONFIG and not isinstance(mapping(text).get("domains"), list):
    path = CONFIG
    text = CONFIG.read_text(encoding="utf-8")
  try:
    return parse(text)
  except DomainConfigError as error:
    raise DomainConfigError(f"{path}: {error}") from error


def _entry(domain: Domain) -> dict[str, str]:
  """Write one Domain, and keep a pinned slug that the name would not make."""
  entry = {"name": domain.name}
  if domain.slug != slugify(domain.name):
    entry["slug"] = domain.slug
  entry["description"] = domain.description
  return entry


def render(found: tuple[Domain, ...]) -> str:
  return yaml.safe_dump(
    {"domains": [_entry(domain) for domain in found]},
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
  return tuple(domain.name for domain in load(db_path))


def find(slug: str, db_path: str | Path | None = None) -> Domain | None:
  for domain in load(db_path):
    if domain.slug == slug:
      return domain
  return None


def slug_for(names: tuple[str, ...], found: tuple[Domain, ...]) -> str:
  """Return the first configured Domain slug in names, else the first slug."""
  by_name = {domain.name: domain.slug for domain in found}
  for name in names:
    if name in by_name:
      return by_name[name]
  return found[0].slug


def domain_slot(names: tuple[str, ...], index: int) -> str:
  """Return the Domain for a fixed demo slot, and wrap a shorter config."""
  if not names:
    raise ValueError("the Domain config lists no name")
  return names[index % len(names)]
