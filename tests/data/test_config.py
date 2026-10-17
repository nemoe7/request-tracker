"""The config file carries settings beside the Domains."""

from pwedepa.data import config, domains


def test_a_file_key_wins_over_its_environment_variable(tmp_path, monkeypatch):
  path = tmp_path / "config.yml"
  path.write_text(
    "domains:\n  - name: Gym\norigin: https://example.com\n", encoding="utf-8"
  )
  monkeypatch.setattr(domains, "CONFIG", path)
  monkeypatch.setenv("PWEDEPA_ORIGIN", "http://localhost:5000")

  found = config.read(tmp_path / "app.db")

  assert config.value(found, "origin", "PWEDEPA_ORIGIN", "x") == "https://example.com"
  assert config.value(found, "rp_id", "PWEDEPA_RP_ID", "fallback") == "fallback"


def test_a_commented_key_leaves_the_environment_in_charge(tmp_path, monkeypatch):
  path = tmp_path / "config.yml"
  path.write_text(
    "domains:\n  - name: Gym\n# origin: https://example.com\n", encoding="utf-8"
  )
  monkeypatch.setattr(domains, "CONFIG", path)
  monkeypatch.setenv("PWEDEPA_ORIGIN", "http://localhost:5000")

  found = config.read(tmp_path / "app.db")

  assert config.value(found, "origin", "PWEDEPA_ORIGIN", "x") == "http://localhost:5000"


def _base_and_dev(tmp_path, monkeypatch):
  base = tmp_path / "config.yml"
  base.write_text(
    "domains:\n  - name: Gym\norigin: https://base.example\nrp_id: base.example\n",
    encoding="utf-8",
  )
  (tmp_path / "config.dev.yml").write_text(
    "domains:\n  - name: Garden\norigin: https://dev.example\n", encoding="utf-8"
  )
  monkeypatch.setattr(domains, "CONFIG", base)
  return base


def test_the_dev_file_beside_the_base_is_read_with_no_variable(tmp_path, monkeypatch):
  _base_and_dev(tmp_path, monkeypatch)

  found = config.read(tmp_path / "app.db")

  assert found["origin"] == "https://dev.example"
  assert "rp_id" not in found, "the dev file stands alone, not on top of config.yml"


def test_without_the_dev_file_the_base_answers(tmp_path, monkeypatch):
  base = tmp_path / "config.yml"
  base.write_text(
    "domains:\n  - name: Gym\norigin: https://base.example\n", encoding="utf-8"
  )
  monkeypatch.setattr(domains, "CONFIG", base)

  assert config.read(tmp_path / "app.db")["origin"] == "https://base.example"


def test_no_environment_variable_moves_the_config(tmp_path, monkeypatch):
  _base_and_dev(tmp_path, monkeypatch)
  elsewhere = tmp_path / "elsewhere.yml"
  elsewhere.write_text("origin: https://elsewhere.example\n", encoding="utf-8")
  for name in ("PWEDEPA_CONFIG", "PWEDEPA_DOMAINS_CONFIG", "PWEDEPA_ENV"):
    monkeypatch.setenv(name, str(elsewhere))

  assert config.read(tmp_path / "app.db")["origin"] == "https://dev.example"


def test_a_dev_file_without_domains_takes_them_from_the_base(tmp_path, monkeypatch):
  base = tmp_path / "config.yml"
  base.write_text("domains:\n  - name: Gym\n", encoding="utf-8")
  (tmp_path / "config.dev.yml").write_text(
    "origin: https://dev.example\n", encoding="utf-8"
  )
  monkeypatch.setattr(domains, "CONFIG", base)

  assert [domain.name for domain in domains.load(tmp_path / "app.db")] == ["Gym"]


def test_a_missing_file_yields_no_settings(tmp_path, monkeypatch):
  monkeypatch.setattr(domains, "CONFIG", tmp_path / "none.yml")

  assert config.read(tmp_path / "app.db") == {}
