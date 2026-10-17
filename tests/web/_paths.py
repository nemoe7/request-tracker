from pwedepa.data import domains as domains_data


def record_url(number: int, kind: str = "requests", names: tuple[str, ...] = ()) -> str:
  found = domains_data.load()
  return f"/{domains_data.slug_for(names, found)}/{kind}/{number}"
