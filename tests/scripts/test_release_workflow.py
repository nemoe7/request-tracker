"""The image set: one workflow builds the dev image, the release tag, and both."""

import json
from pathlib import Path

import gate_workflows
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _document(name: str) -> dict:
  return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _docker() -> dict:
  return _document("docker.yml")


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


def test_each_build_leg_smoke_tests_the_image_it_pushes():
  """A start that cannot find the package must fail the build, not the deploy."""
  jobs = _docker()["jobs"]
  for name in ("dev", "release-build"):
    steps = jobs[name]["steps"]
    smoke = [step for step in steps if step.get("name") == "Smoke Test the Image"]
    assert smoke, f"{name} pushes an image nobody starts"
    assert "import pwedepa" in smoke[0]["run"]


def test_every_image_is_named_pwedepa():
  text = _docker_text()
  assert text.count("ghcr.io/${{ github.repository_owner }}/pwedepa") == 10
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


def test_the_container_scan_watches_the_dependency_inputs():
  """uv.lock and .dockerignore change the image, so the scan watches both."""
  scan = gate_workflows.triggers_of(_document("container-scan.yml"))
  for event in ("push", "pull_request"):
    paths = scan[event]["paths"]
    for path in ("uv.lock", ".dockerignore"):
      assert path in paths, f"the {event} scan misses {path}"


def test_the_dev_commit_tag_comes_from_the_metadata_action():
  """The action makes the commit tag, so the tag and the build arg agree."""
  text = _docker_text()
  assert text.count("type=sha,prefix=dev-") == 2, "both dev jobs tag the commit"
  assert "type=raw,value=${{ steps.dev.outputs.version }}" not in text


def test_the_dev_build_skips_commits_that_change_no_image_input():
  """A docs-only commit needs no new image, so the dev job must not start."""
  jobs = _docker()["jobs"]
  assert "changes" in jobs, "nothing decides whether the commit touches the image"
  assert jobs["dev"]["needs"] == "changes"
  assert "needs.changes.outputs.build == 'yes'" in jobs["dev"]["if"]
  assert jobs["changes"]["outputs"]["build"] == "${{ steps.paths.outputs.build }}"


def test_the_changes_job_reads_the_tested_commit_file_list():
  text = _docker_text()
  assert "commits/$SHA" in text
  assert ".files[].filename" in text
  for path in (
    "pwedepa/*",
    "Dockerfile",
    "config.yml",
    "compose.yml",
    ".dockerignore",
    "pyproject.toml",
    "uv.lock",
  ):
    assert path in text, f"an image input is missing from the change check: {path}"
  assert 'if [[ "$EVENT_NAME" == "workflow_dispatch" ]]' in text, (
    "a manual run always builds"
  )
