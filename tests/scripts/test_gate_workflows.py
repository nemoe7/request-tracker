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


def test_ci_watches_first_party_code_and_docs_only():
  """A skills-only commit checks nothing, so it must not start CI."""
  document = yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
  )
  triggers = gate_workflows.triggers_of(document)
  for event in ("push", "pull_request"):
    paths = triggers[event]["paths"]
    assert "**/*.md" not in paths, f"the {event} list admits the skills tree"
    for doc in ("README.md", "CHANGELOG.md", "docs/**/*.md"):
      assert doc in paths, f"the {event} list misses {doc}"
    assert ".github/workflows/**" in paths, "a workflow edit must run its tests"


def test_ci_watches_the_deployment_files_its_tests_read():
  """A deploy-only commit must run the deploy tests."""
  document = yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
  )
  triggers = gate_workflows.triggers_of(document)
  deploy_files = (
    "Dockerfile",
    "config*.yml",
    "compose*.yml",
    ".env.example",
    ".dockerignore",
  )
  for event in ("push", "pull_request"):
    paths = triggers[event]["paths"]
    for name in deploy_files:
      assert name in paths, f"the {event} list misses {name}"


def test_the_scans_skip_a_skills_only_commit():
  """A skills sync starts no code scan. A code change still does."""
  codeql = yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / "codeql.yml").read_text(encoding="utf-8")
  )
  for event in ("push", "pull_request"):
    paths = gate_workflows.triggers_of(codeql)[event]["paths"]
    for entry in ("pwedepa/**", "tests/**", "scripts/**", ".github/workflows/**"):
      assert entry in paths, f"codeql {event} misses {entry}"
    assert ".agents/**" not in paths, f"codeql {event} admits the skills tree"

  scan = yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / "secret-scan.yml").read_text(encoding="utf-8")
  )
  paths = gate_workflows.triggers_of(scan)["push"]["paths"]
  assert "**" in paths, "the scan keeps its whole-tree default"
  assert "!.agents/**" in paths, "the scan skips the skills tree"
  assert "!ARENA.md" in paths, "the scan skips the agent rules"


def _ci_document() -> dict:
  return yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
  )


def _setup_python_versions(document: dict) -> set[str]:
  versions = set()
  for job in document["jobs"].values():
    for step in job.get("steps", []):
      values = step.get("with")
      if isinstance(values, dict) and "python-version" in values:
        versions.add(str(values["python-version"]))
  return versions


def test_ci_tests_the_image_runtime_and_the_python_floor():
  """Docker runs one Python version while metadata declares a floor range."""
  import re
  import tomllib

  root = gate_workflows.ROOT
  dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
  image = re.search(r"^FROM python:(\d+\.\d+)-", dockerfile, re.MULTILINE)
  assert image, "the runtime stage names no Python version"
  floor = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
  ]["requires-python"]
  floor_version = floor.removeprefix(">=").strip()

  versions = _setup_python_versions(_ci_document())
  assert image.group(1) in versions, "no CI job tests the image runtime"
  assert floor_version in versions, "no CI job tests the declared floor"
  assert versions == {image.group(1), floor_version}, (
    f"CI tests untested-in-production versions: {sorted(versions)}"
  )


def test_no_workflow_repeats_a_key():
  """A repeated key parses without error, and the runner keeps the last one."""
  problems: list[str] = []

  def walk(node, path: str) -> None:
    if isinstance(node, yaml.MappingNode):
      seen: set[str] = set()
      for key, value in node.value:
        name = key.value if hasattr(key, "value") else str(key)
        if name in seen:
          problems.append(f"{path}/{name} at line {key.start_mark.line + 1}")
        seen.add(name)
        walk(value, f"{path}/{name}")
    elif isinstance(node, yaml.SequenceNode):
      for index, item in enumerate(node.value):
        walk(item, f"{path}[{index}]")

  for path in sorted(gate_workflows.WORKFLOW_DIR.glob("*.y*ml")):
    walk(yaml.compose(path.read_text(encoding="utf-8")), path.name)
  assert problems == [], f"duplicate YAML keys: {problems}"


def _steps(name: str) -> list[dict]:
  document = yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / name).read_text(encoding="utf-8")
  )
  return [step for job in document["jobs"].values() for step in job.get("steps", [])]


def test_the_pages_job_pins_uv_and_caches_it():
  """A floating uv can break a deploy with no commit behind the change."""
  setup = next(
    step for step in _steps("pages.yml") if "setup-uv@" in str(step.get("uses"))
  )
  assert setup["with"]["version"] == "0.12.21"
  assert setup["with"]["enable-cache"] is True


def test_the_workflow_gate_installs_one_import():
  """`gate_workflows.py` imports `yaml` and nothing else."""
  text = (gate_workflows.WORKFLOW_DIR / "workflow-security.yml").read_text(
    encoding="utf-8"
  )
  assert "uv sync --locked" not in text, "the workflow gate syncs the whole set"
  steps = [str(step.get("run", "")) for step in _steps("workflow-security.yml")]
  assert any("pyyaml" in step.lower() for step in steps), "the gate needs PyYAML"


def test_ci_skips_the_tests_on_a_docs_only_change():
  """A docs commit still gets the prose lint, and no test run."""
  document = yaml.safe_load(
    (gate_workflows.WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
  )
  jobs = document["jobs"]
  assert "code" in jobs["scope"]["outputs"], "nothing answers the code question"
  assert jobs["scope"]["outputs"]["code"].startswith("${{ steps.paths.outputs")
  for name in ("ci", "floor"):
    steps = jobs[name]["steps"]
    assert jobs[name]["needs"] == "scope", f"{name} runs before the scope answer"
    tests = [step for step in steps if "pytest" in str(step.get("run", ""))]
    assert tests and all(
      "needs.scope.outputs.code" in str(step.get("if")) for step in tests
    ), f"{name} tests a docs-only change"
  prose = [
    step for step in jobs["ci"]["steps"] if "nemoizer" in str(step.get("run", ""))
  ]
  assert prose and "if" not in prose[0], "the prose lint must run on every change"


def test_the_uv_pins_match_the_newest_release():
  """A pin one minor behind drifts without a commit."""
  text = " ".join(
    (gate_workflows.WORKFLOW_DIR / name).read_text(encoding="utf-8")
    for name in (
      "ci.yml",
      "dependency-review.yml",
      "pages.yml",
      "workflow-security.yml",
    )
  )
  assert "setup-uv@v10.3.0" in text
  assert "setup-uv@v10.2.0" not in text
