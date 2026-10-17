"""Record paths for the web tests: the Domain segment comes from the config."""

from pwedepa.data import domains as domains_data


def record_url(number: int, kind: str = "requests", names: tuple[str, ...] = ()) -> str:
  """Return the path for one record under its first configured Domain."""
  found = domains_data.load()
  return f"/{domains_data.slug_for(names, found)}/{kind}/{number}"
