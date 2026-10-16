"""The starter Domains come from one json config, and the stub seeds with them."""

import subprocess
import sys
from pathlib import Path

import pytest

from pwedepa.data import db as data_db
from pwedepa.data import domains as domains_data
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.data.domains import CONFIG, domain_slot, starter_domains

ROOT = Path(__file__).resolve().parents[2]


def test_the_config_lists_unique_domains_in_order():
  names = starter_domains()
  assert len(names) > 2, "the demo needs more than one Domain"
  assert len(set(names)) == len(names), "each Domain reads once"
  assert list(names) == sorted(names), "the rail shows this order"


def test_the_config_sits_at_the_project_root():
  assert CONFIG.name == "domains.json"
  assert CONFIG.parent == ROOT, "the operator edits the config at the root"
  assert CONFIG.is_file(), "the deploy files carry the config to the image"


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
  monkeypatch.setattr(domains_data, "CONFIG", tmp_path / "domains.json")
  with pytest.raises(FileNotFoundError) as error:
    domains_data.starter_domains()
  message = str(error.value)
  assert "domains.json is missing" in message
  assert str(ROOT / "domains.json") in message
  assert str(Path("domains.json").resolve()) in message


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
