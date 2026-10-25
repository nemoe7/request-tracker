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
  assert "COPY config.yml ./" in text, "the image carries the config template"


def test_the_image_carries_the_package_it_starts():
  """A bare venv cannot import `pwedepa` when editable installs point at missing source."""
  stages = (ROOT / "Dockerfile").read_text(encoding="utf-8").split("\nFROM ")
  runtime = stages[-1]
  sync = next(line for line in stages if "uv sync" in line)
  copies_source = re.search(r"^COPY pwedepa ./", runtime, re.MULTILINE)

  assert copies_source or "--no-editable" in sync, (
    "the runtime stage installs an editable package and leaves its source behind"
  )


def test_the_image_names_its_build():
  """Headers read a build-written version stamp because image contexts exclude `.git`."""
  text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
  assert "ARG VERSION=" in text
  assert "pwedepa/_version.txt" in text


def test_the_config_sits_at_the_repo_root():
  assert (ROOT / "config.yml").is_file()


def test_compose_names_every_container():
  services = _compose()["services"]
  assert list(services) == ["pwedepa", "tailscale"]
  assert services["pwedepa"]["container_name"] == "pwedepa-app"
  assert services["tailscale"]["container_name"] == "pwedepa-tailscale"


def test_compose_mounts_the_config_read_only():
  service = _compose()["services"]["pwedepa"]
  mounts = [str(volume) for volume in service["volumes"]]
  assert "./config.yml:/app/config.yml:ro" in mounts
  assert "PWEDEPA_CONFIG" not in service["environment"], (
    "the app reads the file at its own path, not one an env var names"
  )


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
  mounts = [str(volume) for volume in service["volumes"]]
  assert any(volume.startswith("pwedepa-dev-data:/data") for volume in mounts)
  assert "./config.dev.yml:/app/config.dev.yml:ro" in mounts, (
    "the dev file sits beside config.yml, where the app reads it whole"
  )


def test_compose_runs_the_tailscale_sidecar_for_the_funnel():
  sidecar = _compose()["services"]["tailscale"]
  assert sidecar["image"].startswith("tailscale/tailscale")
  assert sidecar["environment"]["TS_HOSTNAME"] == "pwedepa"
  assert sidecar["environment"]["TS_SERVE_CONFIG"] == "/config/serve.json"
  assert sidecar["environment"]["TS_STATE_DIR"] == "/var/lib/tailscale"
  assert sidecar["environment"]["TS_ENABLE_HEALTH_CHECK"] == "true", (
    "the image serves /healthz only when the flag is on"
  )
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


def test_the_sidecar_reports_its_own_health():
  """A wait for the sidecar must see the node, not only a live process."""
  sidecar = _compose()["services"]["tailscale"]
  probe = sidecar["healthcheck"]
  assert probe["test"][0] == "CMD"
  assert "9002/healthz" in " ".join(probe["test"]), "the node answers here"
  assert int(str(probe["interval"]).rstrip("s")) >= 10
  assert int(str(probe["retries"]).rstrip("s")) >= 3


def test_the_app_container_reports_its_own_health():
  """Compose waits on the app, so a wait must see the app answer."""
  service = _compose()["services"]["pwedepa"]
  probe = service["healthcheck"]
  assert probe["test"][0] == "CMD"
  command = " ".join(probe["test"])
  assert "urllib.request" in command, "the app image carries python, not wget"
  assert "'/health'" in command, "the probe must read the route the app serves"
  assert "wget" not in command
