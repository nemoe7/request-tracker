from __future__ import annotations

import copy

import gate_workflows
import yaml

BASE = {
  "name": "Example",
  "on": {"push": {"branches": ["main"]}, "workflow_dispatch": None},
  "permissions": {"contents": "read"},
  "jobs": {
    "work": {
      "runs-on": "ubuntu-latest",
      "steps": [{"name": "Run", "run": "echo ok"}],
    }
  },
}


def findings(document: dict, name: str = "example.yml") -> list[str]:
  return gate_workflows.audit_document(name, copy.deepcopy(document))


def test_base_document_passes():
  assert findings(BASE) == []


def test_real_workflow_set_passes():
  assert gate_workflows.audit_paths() == []


def test_required_file_set_is_exact():
  assert gate_workflows.REQUIRED_FILES == (
    "ci.yml",
    "codeql.yml",
    "container-scan.yml",
    "dependency-review.yml",
    "docker.yml",
    "pages.yml",
    "pr-check.yml",
    "secret-scan.yml",
    "workflow-security.yml",
  )
  assert gate_workflows.EXEMPT_FILES == ("gemini-release.yml",)
  assert gate_workflows.WORKFLOW_RUN_FILES == ("docker.yml",)


def write_set(directory, names) -> None:
  for name in names:
    (directory / name).write_text(yaml.safe_dump(BASE), encoding="utf-8")


def test_missing_required_file_fails(tmp_path):
  write_set(tmp_path, gate_workflows.REQUIRED_FILES[:-1])
  result = gate_workflows.audit_paths(tmp_path)
  assert any("required workflow file is missing" in finding for finding in result)


def test_extra_workflow_file_fails(tmp_path):
  write_set(tmp_path, gate_workflows.REQUIRED_FILES)
  (tmp_path / "extra.yml").write_text(yaml.safe_dump(BASE), encoding="utf-8")
  result = gate_workflows.audit_paths(tmp_path)
  assert any("unexpected workflow file" in finding for finding in result)


def test_exempt_file_is_not_audited(tmp_path):
  write_set(tmp_path, gate_workflows.REQUIRED_FILES)
  (tmp_path / "gemini-release.yml").write_text("name: [unclosed\n", encoding="utf-8")
  assert gate_workflows.audit_paths(tmp_path) == []


def test_invalid_yaml_fails(tmp_path):
  (tmp_path / "ci.yml").write_text("name: [unclosed\n", encoding="utf-8")
  result = gate_workflows.audit_paths(tmp_path)
  assert any("invalid YAML" in finding for finding in result)


def test_missing_permissions_fails():
  document = copy.deepcopy(BASE)
  del document["permissions"]
  assert any("top-level `permissions`" in finding for finding in findings(document))


def test_write_scope_at_top_level_fails():
  document = copy.deepcopy(BASE)
  document["permissions"]["contents"] = "write"
  assert any("must stay read-only" in finding for finding in findings(document))


def test_workflow_run_fails():
  document = copy.deepcopy(BASE)
  document["on"]["workflow_run"] = {"workflows": ["CI"]}
  assert any("workflow_run" in finding for finding in findings(document))


def test_the_named_file_may_watch_a_run():
  document = copy.deepcopy(BASE)
  document["on"]["workflow_run"] = {"workflows": ["CI"]}
  assert findings(document, name="docker.yml") == []
  assert any("workflow_run" in finding for finding in findings(document, name="ci.yml"))


def test_pull_request_target_passes():
  document = copy.deepcopy(BASE)
  document["on"]["pull_request_target"] = None
  assert findings(document) == []


def test_workflow_level_secret_fails():
  document = copy.deepcopy(BASE)
  document["env"] = {"TOKEN": "${{ secrets.TOKEN }}"}
  assert any("must stay inside a job" in finding for finding in findings(document))


def test_secret_in_a_run_step_fails():
  document = copy.deepcopy(BASE)
  document["jobs"]["work"]["steps"] = [
    {"name": "Run", "run": 'echo "${{ secrets.TOKEN }}"'}
  ]
  assert any(
    "must not appear in a step `run`" in finding for finding in findings(document)
  )


def test_main_exit_codes(capsys):
  assert gate_workflows.main([]) == 0
  assert "Workflow set passed" in capsys.readouterr().out
