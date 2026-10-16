"""The image set: one workflow builds the dev image, the release tag, and both."""

import json
from pathlib import Path

import gate_workflows
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _docker() -> dict:
  text = (WORKFLOWS / "docker.yml").read_text(encoding="utf-8")
  return yaml.safe_load(text)


def _docker_text() -> str:
  return (WORKFLOWS / "docker.yml").read_text(encoding="utf-8")


def test_the_image_workflow_follows_main_and_the_release_draft():
  triggers = gate_workflows.triggers_of(_docker())
  assert triggers["push"]["tags"] == ["v*"]
  assert triggers["workflow_run"]["workflows"] == ["CI", "Gemini Release Draft"]
  assert triggers["workflow_run"]["types"] == ["completed"]
  assert "workflow_dispatch" in triggers


def test_only_the_image_workflow_may_watch_a_run():
  assert gate_workflows.WORKFLOW_RUN_FILES == ("docker.yml",)


def test_the_release_job_reads_the_approved_tag_from_the_draft_run():
  text = _docker_text()
  assert 'select(.name == "draft")' in text
  assert 'select(.name == "Approve Proposal")' in text
  assert "Tag [\\x60](v[0-9]+\\.[0-9]+\\.[0-9]+)[\\x60] points to" in text


def test_the_release_build_checks_the_approved_commit():
  text = _docker_text()
  assert 'git rev-list -n 1 "$TAG^{commit}"' in text
  assert "expected_sha" in text


def test_every_image_is_named_pwedepa():
  text = _docker_text()
  assert text.count("ghcr.io/${{ github.repository_owner }}/pwedepa") == 8
  assert "PACKAGE" in text
  assert "REPO: ${{ github.repository_owner }}/pwedepa" in text


def test_the_dev_tags_keep_the_moving_name_and_the_commit():
  text = _docker_text()
  assert "type=raw,value=dev" in text
  assert "version=dev-%s" in text


def test_latest_moves_only_for_the_newest_release_tag():
  text = _docker_text()
  assert "matching-refs/tags/v" in text, "the newest tag decides latest"
  assert text.count("type=raw,value=latest,enable=") == 2
  assert _docker()["jobs"]["release"]["outputs"]["latest"] == (
    "${{ steps.release.outputs.latest }}"
  )


def test_the_release_tags_carry_the_release_and_latest():
  text = _docker_text()
  assert "type=raw,value=${{ needs.release.outputs.tag }}" in text
  assert text.count("type=raw,value=latest") == 2
  for job in ("release-build", "release-merge", "dev", "dev-merge"):
    assert _docker()["jobs"][job]["permissions"]["packages"] == "write"


def test_the_evidence_policy_keeps_the_deployment_files():
  text = (WORKFLOWS / "gemini-release-evidence.json").read_text(encoding="utf-8")
  policy = json.loads(text)
  assert list(policy) == ["include", "exclude"]
  for noise in ("tests/**", "scripts/**", ".github/**"):
    assert noise in policy["exclude"]
  for kept in ("Dockerfile", "compose.yml", "domains.json"):
    assert kept not in policy["exclude"]
