"""The Domains come from one YAML config, and the stub seeds with them."""

import subprocess
import sys
from pathlib import Path

import pytest

from pwedepa.data import db as data_db
from pwedepa.data import domains as domains_data
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.data.domains import CONFIG, DomainConfigError, domain_slot, starter_domains

ROOT = Path(__file__).resolve().parents[2]


def test_the_config_lists_unique_domains_in_order():
  names = starter_domains()
  assert len(names) > 2, "the demo needs more than one Domain"
  assert len(set(names)) == len(names), "each Domain reads once"
  assert list(names) == sorted(names), "the rail shows this order"


def test_every_domain_carries_a_slug_and_a_description():
  found = domains_data.load()
  assert len(found) == len(starter_domains())
  assert all(domain.slug for domain in found), "a URL needs a slug"
  assert all(domain.description for domain in found), "the page shows the description"
  assert len({domain.slug for domain in found}) == len(found), "slugs stay unique"


def test_the_config_sits_at_the_project_root():
  assert CONFIG.name == "domains.yaml"
  assert CONFIG.parent == ROOT, "the operator edits the config at the root"
  assert CONFIG.is_file(), "the deploy files carry the config to the image"


def test_a_slug_is_lowercase_and_joins_words():
  assert domains_data.slugify("3D Print/Model") == "3d-print-model"
  assert domains_data.slugify("Handyman / DIY") == "handyman-diy"
  assert domains_data.slugify("Gym") == "gym"
  assert domains_data.slugify("  --  ") == ""


def test_a_short_config_wraps_instead_of_stopping_the_seed():
  assert domain_slot(("Gym",), 5) == "Gym", "one name fills every slot"
  assert domain_slot(("Gym", "Handyman/DIY"), 3) == "Handyman/DIY", "the names cycle"


def test_no_caller_indexes_the_config_by_position():
  for path in (
    ROOT / "scripts" / "demo_seed.py",
    ROOT / "pwedepa" / "web" / "routes" / "demo.py",
  ):
    assert "names[" not in path.read_text(encoding="utf-8"), path


def test_a_missing_config_names_the_file_and_both_paths(monkeypatch, tmp_path):
  db_path = tmp_path / "app.db"
  monkeypatch.setattr(domains_data, "CONFIG", tmp_path / "domains.yaml")
  monkeypatch.delenv("PWEDEPA_DOMAINS_CONFIG", raising=False)
  with pytest.raises(FileNotFoundError) as error:
    domains_data.load(db_path)
  assert str(tmp_path / "domains.yaml") in str(error.value)


def test_a_duplicate_slug_stops_the_import():
  with pytest.raises(DomainConfigError) as error:
    domains_data.parse("domains:\n  - name: Gym\n  - name: gym\n")
  assert "gym" in str(error.value)


def test_an_empty_config_stops_the_import():
  with pytest.raises(DomainConfigError):
    domains_data.parse("domains: []\n")


def test_a_config_entry_needs_a_name():
  with pytest.raises(DomainConfigError) as error:
    domains_data.parse("domains:\n  - description: no name\n")
  assert "name" in str(error.value)


def test_the_imported_copy_wins_over_the_packaged_file(tmp_path):
  db_path = tmp_path / "app.db"
  imported = domains_data.imported_path(db_path)
  imported.write_text(
    "domains:\n  - name: Garden\n    description: Plots and tools.\n",
    encoding="utf-8",
  )
  found = domains_data.load(db_path)
  assert [domain.name for domain in found] == ["Garden"]
  assert domains_data.find("garden", db_path).description == "Plots and tools."


def test_the_stub_seeds_only_configured_domains(tmp_path):
  database = tmp_path / "demo.db"
  done = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "demo_seed.py"), str(database)],
    cwd=ROOT,
    capture_output=True,
    text=True,
    timeout=120,
    check=False,
  )
  assert done.returncode == 0, done.stderr

  connection = data_db.connect(str(database))
  try:
    found = {
      name
      for record in requests_data.list_requests(connection)
      for name in record.domains
    }
    found |= {
      name for issue in issues_data.list_issues(connection) for name in issue.domains
    }
  finally:
    connection.close()
  assert found == set(starter_domains()), "every configured Domain shows in the stub"


def test_a_pinned_slug_survives_a_rename():
  found = domains_data.parse(
    "domains:\n  - name: Gym and Climbing\n    slug: gym\n    description: Training.\n"
  )
  assert found[0].slug == "gym"
  assert found[0].name == "Gym and Climbing"


def test_a_pinned_slug_must_be_a_url_segment():
  with pytest.raises(DomainConfigError):
    domains_data.parse("domains:\n  - name: Gym\n    slug: Gym / Hall\n")
