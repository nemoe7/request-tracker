"""The config file carries settings beside the Domains."""

from pwedepa.data import config, domains


def _clean(monkeypatch):
  monkeypatch.delenv("PWEDEPA_CONFIG", raising=False)
  monkeypatch.delenv("PWEDEPA_DOMAINS_CONFIG", raising=False)


def test_a_file_key_wins_over_its_environment_variable(tmp_path, monkeypatch):
  path = tmp_path / "config.yml"
  path.write_text(
    "domains:\n  - name: Gym\norigin: https://example.com\n", encoding="utf-8"
  )
  monkeypatch.setattr(domains, "CONFIG", path)
  _clean(monkeypatch)
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
  _clean(monkeypatch)
  monkeypatch.setenv("PWEDEPA_ORIGIN", "http://localhost:5000")

  found = config.read(tmp_path / "app.db")

  assert config.value(found, "origin", "PWEDEPA_ORIGIN", "x") == "http://localhost:5000"


def test_a_missing_file_yields_no_settings(tmp_path, monkeypatch):
  monkeypatch.setattr(domains, "CONFIG", tmp_path / "none.yml")
  _clean(monkeypatch)

  assert config.read(tmp_path / "app.db") == {}
