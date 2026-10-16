"""Pages demo: one workflow freezes the seeded demo into static pages."""

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
LINK_RE = re.compile(r'(?:href|action|src)="([^"]+)"')


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


def test_frozen_demo_opens_rail_filters_and_selected_records(tmp_path):
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
  queue = re.search(r'href="\./(workspace/queue/mine)/"[^>]*>My requests', index)
  assert queue, "a queue link should open its own frozen page"
  page = (out / queue.group(1) / "index.html").read_text(encoding="utf-8")
  assert re.search(r'class="queue-item is-active"[^>]*>My requests', page)
  record = re.search(r'href="\./(workspace/record/\d+)/"[^>]*>[^<]+</a>', index)
  assert record, "a record row should open its own frozen page"
  page = (out / record.group(1) / "index.html").read_text(encoding="utf-8")
  assert '<tr class="is-selected">' in page


def test_frozen_demo_ships_no_writes_and_no_dead_links(tmp_path):
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
  pages = sorted(out.rglob("index.html"))
  assert pages
  for page in pages:
    html = page.read_text(encoding="utf-8")
    assert 'method="post"' not in html, page
    for target in LINK_RE.findall(html):
      if target.startswith(("#", "http", "mailto:", "data:")):
        continue
      assert not target.startswith("/"), (page, target)
      path = (page.parent / target.split("?")[0].split("#")[0]).resolve()
      assert path.exists(), (page, target)
