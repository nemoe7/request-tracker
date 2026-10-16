"""Pages demo: one workflow freezes the seeded demo into static pages."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


def test_pages_workflow_builds_and_deploys():
  document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
  text = WORKFLOW.read_text(encoding="utf-8")
  assert "build_pages_demo.py" in text
  assert "actions/upload-pages-artifact" in text
  assert "actions/deploy-pages" in text
  triggers = document.get("on", document.get(True))
  assert "pull_request" not in triggers
  job = document["jobs"]["deploy"]
  assert job["permissions"]["pages"] == "write"
  assert job["permissions"]["id-token"] == "write"


def test_frozen_demo_keeps_pages_and_assets_relative(tmp_path):
  out = tmp_path / "site"
  env = {**os.environ, "PWEDEPA_PAGES_OUT": str(out)}
  result = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "build_pages_demo.py")],
    cwd=ROOT,
    env=env,
    capture_output=True,
    text=True,
    timeout=120,
    check=False,
  )
  assert result.returncode == 0, result.stderr
  index = (out / "index.html").read_text(encoding="utf-8")
  assert "Broken projector in Room 4" in index
  assert 'href="/static' not in index
  assert 'src="/static' not in index
  assert (out / "static" / "app.css").exists()
  assert (out / "settings" / "index.html").exists()
  assert (out / "home" / "index.html").exists()
