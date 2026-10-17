"""A first start fills an empty database from the seed block in force."""

from pwedepa.data import db, domains, requests
from pwedepa.web import create_app, seed_first_start

SEED_BLOCK = (
  "seed:\n"
  "  - kind: request\n"
  "    title: A leak\n"
  "    description: Under the sink.\n"
  "    domain: Gym\n"
)


def _app(tmp_path, monkeypatch, *, dev_seed):
  base = tmp_path / "config.yml"
  base.write_text("domains:\n  - name: Gym\n", encoding="utf-8")
  if dev_seed:
    (tmp_path / "config.dev.yml").write_text(
      "domains:\n  - name: Gym\n" + SEED_BLOCK, encoding="utf-8"
    )
  monkeypatch.setattr(domains, "CONFIG", base)
  return create_app({"DATABASE": str(tmp_path / "app.db")})


def _titles(app):
  connection = db.connect(app.config["DATABASE"])
  try:
    return [row.title for row in requests.list_requests(connection)]
  finally:
    connection.close()


def test_a_first_start_inserts_the_dev_seed_rows(tmp_path, monkeypatch):
  app = _app(tmp_path, monkeypatch, dev_seed=True)

  assert seed_first_start(app) == 1
  assert _titles(app) == ["A leak"]


def test_a_config_without_a_seed_block_inserts_nothing(tmp_path, monkeypatch):
  app = _app(tmp_path, monkeypatch, dev_seed=False)

  assert seed_first_start(app) == 0
  assert _titles(app) == []


def test_a_second_start_adds_no_row_again(tmp_path, monkeypatch):
  app = _app(tmp_path, monkeypatch, dev_seed=True)

  assert seed_first_start(app) == 1
  assert seed_first_start(app) == 0
  assert _titles(app) == ["A leak"]
