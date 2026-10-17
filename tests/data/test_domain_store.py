"""The domains table starts from the file, then holds its own list."""

from pwedepa.data import domain_store, domains

LIST = (
  "domains:\n"
  "  - name: Gym\n"
  "    description: Training plans.\n"
  "  - name: Garden\n"
  "    description: Plots and tools.\n"
)


def _settings(text):
  return domains.mapping(text)


def test_the_table_starts_empty(tmp_path):
  assert domain_store.read_all(tmp_path / "app.db") == ()


def test_the_file_fills_an_empty_table(tmp_path):
  path = tmp_path / "app.db"
  assert domain_store.seed_from_file(path, _settings(LIST)) == 2
  assert [domain.name for domain in domain_store.read_all(path)] == ["Gym", "Garden"]
  assert [domain.slug for domain in domain_store.read_all(path)] == ["gym", "garden"]


def test_a_second_seed_changes_nothing(tmp_path):
  path = tmp_path / "app.db"
  domain_store.seed_from_file(path, _settings(LIST))
  assert domain_store.seed_from_file(path, _settings("domains:\n  - name: Shop\n")) == 0
  assert [domain.name for domain in domain_store.read_all(path)] == ["Gym", "Garden"]


def test_an_empty_list_seeds_nothing(tmp_path):
  assert domain_store.seed_from_file(tmp_path / "app.db", {}) == 0
  assert domain_store.read_all(tmp_path / "app.db") == ()


def test_a_duplicate_slug_stops_the_seed(tmp_path):
  text = "domains:\n  - name: Gym\n  - name: gym\n"
  try:
    domain_store.seed_from_file(tmp_path / "app.db", _settings(text))
  except domains.DomainConfigError:
    pass
  else:
    raise AssertionError("a duplicate slug must stop the seed")


AT = __import__("datetime").datetime(
  2026, 10, 17, 12, 0, tzinfo=__import__("datetime").UTC
)


def _with_request(path):
  from pwedepa.core import Request, RequestStatus, Visibility
  from pwedepa.data import db as data_db
  from pwedepa.data import requests as requests_data

  connection = data_db.connect(path)
  try:
    requests_data.save(
      connection,
      Request(
        id=0,
        title="A leak",
        description="Under the sink.",
        status=RequestStatus.OPEN,
        visibility=Visibility.PUBLIC,
        domains=("Gym",),
        created_at=AT,
        updated_at=AT,
      ),
      commit=True,
    )
  finally:
    connection.close()


def test_count_records_names_what_a_remove_drops(tmp_path):
  path = tmp_path / "app.db"
  domain_store.seed_from_file(path, _settings(LIST))
  _with_request(path)

  assert domain_store.count_records(path, "gym") == (1, 0, 0)


def test_remove_drops_the_domain_and_its_records(tmp_path):
  path = tmp_path / "app.db"
  domain_store.seed_from_file(path, _settings(LIST))
  _with_request(path)

  assert domain_store.remove(path, "gym") == (1, 0, 0)
  assert [domain.name for domain in domain_store.read_all(path)] == ["Garden"]


def test_remove_of_an_unknown_slug_raises(tmp_path):
  from pwedepa.data import domains

  try:
    domain_store.remove(tmp_path / "app.db", "nowhere")
  except domains.DomainConfigError:
    pass
  else:
    raise AssertionError("an unknown slug must raise")
