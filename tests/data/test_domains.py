"""The starter Domains come from one json config, and the stub seeds with them."""

import subprocess
import sys
from pathlib import Path

from pwedepa.data import db as data_db
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.data.domains import CONFIG, starter_domains

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
