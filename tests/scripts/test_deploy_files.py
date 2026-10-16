"""Deployment files: one app container, one Tailscale sidecar, one Funnel proxy."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict:
  return yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))


def test_dockerfile_runs_the_web_app_as_one_service():
  text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
  assert "pwedepa.web" in text
  assert "PWEDEPA_HOST" in text
  assert "USER" in text
  assert "COPY domains.json ./" in text, "the image carries the domains config"


def test_the_domains_config_sits_at_the_repo_root():
  assert (ROOT / "domains.json").is_file()


def test_compose_names_every_container():
  services = _compose()["services"]
  assert list(services) == ["pwedepa", "tailscale"]
  assert services["pwedepa"]["container_name"] == "pwedepa-app"
  assert services["tailscale"]["container_name"] == "pwedepa-tailscale"


def test_compose_keeps_the_app_data_on_a_volume():
  service = _compose()["services"]["pwedepa"]
  assert service["build"] == "."
  assert any(
    str(volume).startswith("pwedepa-data:/data") for volume in service["volumes"]
  )


def test_compose_runs_the_tailscale_sidecar_for_the_funnel():
  sidecar = _compose()["services"]["tailscale"]
  assert sidecar["image"].startswith("tailscale/tailscale")
  assert sidecar["environment"]["TS_SERVE_CONFIG"] == "/config/tailscale-funnel.json"
  assert sidecar["environment"]["TS_STATE_DIR"] == "/var/lib/tailscale"
  mounts = [str(volume) for volume in sidecar["volumes"]]
  assert "./tailscale-funnel.json:/config/tailscale-funnel.json:ro" in mounts
  assert "tailscale-state:/var/lib/tailscale" in mounts


def test_tailscale_funnel_json_proxies_to_the_app_service():
  document = json.loads((ROOT / "tailscale-funnel.json").read_text(encoding="utf-8"))
  web = document["Web"]
  assert web
  handlers = next(iter(web.values()))["Handlers"]
  assert next(iter(handlers.values()))["Proxy"] == "http://pwedepa:5000"
