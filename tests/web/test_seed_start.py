"""A dev start fills an empty database from the config seed."""

from pwedepa.data import db, domains, requests
from pwedepa.web import create_app

SEED_CONFIG = (
  "domains:\n"
  "  - name: Gym\n"
  "seed:\n"
  "  - kind: request\n"
  "    title: A leak\n"
  "    description: Under the sink.\n"
  "    domain: Gym\n"
)


def test_a_dev_start_inserts_the_seed_rows(tmp_path, monkeypatch):
  config = tmp_path / "config.yml"
  config.write_text(SEED_CONFIG, encoding="utf-8")
  monkeypatch.setattr(domains, "CONFIG", config)
  monkeypatch.setenv("PWEDEPA_ENV", "dev")

  app = create_app({"DATABASE": str(tmp_path / "app.db")})

  connection = db.connect(app.config["DATABASE"])
  assert [row.title for row in requests.list_requests(connection)] == ["A leak"]


def test_a_release_start_ignores_the_seed(tmp_path, monkeypatch):
  config = tmp_path / "config.yml"
  config.write_text(SEED_CONFIG, encoding="utf-8")
  monkeypatch.setattr(domains, "CONFIG", config)
  monkeypatch.delenv("PWEDEPA_ENV", raising=False)

  app = create_app({"DATABASE": str(tmp_path / "app.db")})

  connection = db.connect(app.config["DATABASE"])
  assert requests.list_requests(connection) == []
