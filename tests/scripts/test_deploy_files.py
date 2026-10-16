"""Deployment files: one app container, one Tailscale sidecar, one Funnel proxy."""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _compose(name: str = "compose.yml") -> dict:
  return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


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


def test_deploy_compose_pulls_the_published_image():
  service = _compose()["services"]["pwedepa"]
  assert "build" not in service, "the deploy runs the published image, not the checkout"
  assert service["image"] == "ghcr.io/nemoe7/pwedepa:latest"


def test_dev_compose_builds_the_checkout_locally():
  document = _compose("compose.dev.yml")
  assert list(document["services"]) == ["pwedepa"], "a local build needs no sidecar"
  service = document["services"]["pwedepa"]
  assert service["build"] == "."
  assert service["image"] == "pwedepa:dev"
  assert service["container_name"] == "pwedepa-dev"
  assert any(
    str(volume).startswith("pwedepa-dev-data:/data") for volume in service["volumes"]
  )


def test_compose_runs_the_tailscale_sidecar_for_the_funnel():
  sidecar = _compose()["services"]["tailscale"]
  assert sidecar["image"].startswith("tailscale/tailscale")
  assert sidecar["environment"]["TS_HOSTNAME"] == "pwedepa"
  assert sidecar["environment"]["TS_SERVE_CONFIG"] == "/config/serve.json"
  assert sidecar["environment"]["TS_STATE_DIR"] == "/var/lib/tailscale"
  assert "TS_CERT_DOMAIN" not in sidecar["environment"], (
    "the sidecar fills the cert domain placeholder itself"
  )
  mounts = [str(volume) for volume in sidecar["volumes"]]
  assert "./tailscale:/config:ro" in mounts
  assert "tailscale-state:/var/lib/tailscale" in mounts


def test_tailscale_funnel_json_proxies_to_the_app_service():
  document = json.loads((ROOT / "tailscale" / "serve.json").read_text(encoding="utf-8"))
  web = document["Web"]
  assert web
  handlers = next(iter(web.values()))["Handlers"]
  assert next(iter(handlers.values()))["Proxy"] == "http://pwedepa:5000"


def test_compose_requires_its_own_session_secret():
  text = (ROOT / "compose.yml").read_text(encoding="utf-8")
  assert "${PWEDEPA_SECRET_KEY:?" in text, "a deploy must supply its own session secret"


def test_env_example_lists_every_variable_compose_reads():
  text = "\n".join(
    path.read_text(encoding="utf-8") for path in sorted(ROOT.glob("compose*.yml"))
  )
  example = (ROOT / ".env.example").read_text(encoding="utf-8")
  names = sorted(set(re.findall(r"\$\{([A-Z_]+)", text)))
  assert names, "compose reads no variable at all"
  missing = [name for name in names if f"{name}=" not in example]
  assert not missing, f".env.example misses {missing}"


def test_compose_requires_its_own_auth_key():
  text = (ROOT / "compose.yml").read_text(encoding="utf-8")
  assert "${TS_AUTHKEY:?" in text, "a deploy must supply its own auth key"


def test_the_sidecar_mounts_the_config_folder():
  text = (ROOT / "compose.yml").read_text(encoding="utf-8")
  assert "./tailscale:/config:ro" in text, "a single-file mount hides config edits"
  assert (ROOT / "tailscale" / "serve.json").is_file()


def test_the_dev_compose_takes_the_origin_from_the_environment():
  document = _compose("compose.dev.yml")
  origin = document["services"]["pwedepa"]["environment"]["PWEDEPA_ORIGIN"]
  assert origin.startswith("${PWEDEPA_ORIGIN:-"), (
    "a local build must accept its own origin, for a phone on the LAN"
  )
