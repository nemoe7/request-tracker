"""The release path: a gemini draft that tags, and a tag that builds the image."""

import json
from pathlib import Path

import gate_workflows
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _document(name: str) -> dict:
  text = (WORKFLOWS / name).read_text(encoding="utf-8")
  return json.loads(text) if name.endswith(".json") else yaml.safe_load(text)


def test_the_gemini_release_workflow_keeps_its_helper():
  workflow = (WORKFLOWS / "gemini-release.yml").read_text(encoding="utf-8")
  assert "python .github/workflows/gemini_release.py" in workflow
  assert (WORKFLOWS / "gemini_release.py").is_file()


def test_the_evidence_policy_keeps_the_deployment_files():
  policy = _document("gemini-release-evidence.json")
  assert list(policy) == ["include", "exclude"]
  for noise in ("tests/**", "scripts/**", ".github/**"):
    assert noise in policy["exclude"]
  for kept in ("Dockerfile", "compose.yml", "domains.json"):
    assert kept not in policy["exclude"]


def test_the_docker_release_workflow_builds_from_a_version_tag():
  triggers = gate_workflows.triggers_of(_document("docker-release.yml"))
  assert triggers["push"]["tags"] == ["v*"]
  assert "workflow_dispatch" in triggers
  assert "workflow_run" not in triggers


def test_the_release_workflow_takes_a_tag_by_hand():
  # The README sends the operator here with the approved tag, so the input stays.
  triggers = gate_workflows.triggers_of(_document("docker-release.yml"))
  assert triggers["workflow_dispatch"]["inputs"]["tag"]["required"] is True


def test_the_release_job_publishes_the_semver_and_latest_tags():
  job = _document("docker-release.yml")["jobs"]["release"]
  assert job["permissions"]["packages"] == "write"
  text = (WORKFLOWS / "docker-release.yml").read_text(encoding="utf-8")
  assert "type=semver,pattern={{version}}" in text
  assert "type=raw,value=latest" in text
  assert "ghcr.io/${{ github.repository_owner }}/pwedepa" in text
