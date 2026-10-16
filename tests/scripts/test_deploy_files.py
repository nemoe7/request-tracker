"""Deployment files: one container, one compose service, one Funnel proxy."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_runs_the_web_app_as_one_service():
  text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
  assert "pwedepa.web" in text
  assert "PWEDEPA_HOST" in text
  assert "USER" in text
  assert "COPY domains.json ./" in text, "the image carries the domains config"


def test_the_domains_config_sits_at_the_repo_root():
  assert (ROOT / "domains.json").is_file()


def test_compose_defines_one_service_with_a_data_volume():
  document = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
  services = document["services"]
  assert list(services) == ["pwedepa"]
  service = services["pwedepa"]
  assert service["build"] == "."
  assert any(
    str(volume).startswith("pwedepa-data:/data") for volume in service["volumes"]
  )


def test_tailscale_funnel_json_proxies_to_the_app():
  document = json.loads((ROOT / "tailscale-funnel.json").read_text(encoding="utf-8"))
  web = document["Web"]
  assert web
  handlers = next(iter(web.values()))["Handlers"]
  assert next(iter(handlers.values()))["Proxy"] == "http://127.0.0.1:5000"
