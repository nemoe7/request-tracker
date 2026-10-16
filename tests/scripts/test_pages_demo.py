"""Pages demo: one workflow freezes the seeded demo into static pages."""

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"
LINK_RE = re.compile(r'(?:href|action|src)="([^"]+)"')
SITE = "https://example.test/demo/"
DEMO_RE = re.compile(r'(?:href|action|src|data-src)="([^"]+)"')


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
  queue = re.search(r'href="(workspace/queue/mine)/"[^>]*>My requests', index)
  assert queue, "a queue link should open its own frozen page"
  page = (out / queue.group(1) / "index.html").read_text(encoding="utf-8")
  assert re.search(r'class="queue-item is-active"[^>]*>My requests', page)
  record = re.search(r'href="(workspace/record/\d+)/"[^>]*>[^<]+</a>', index)
  assert record, "a record row should open its own frozen page"
  page = (out / record.group(1) / "index.html").read_text(encoding="utf-8")
  assert '<tr class="is-selected">' in page


def test_the_frozen_rail_offers_one_link_per_status(tmp_path):
  """A file host ignores a form query, so every status needs a page and a link."""
  out = _frozen_site(tmp_path)
  page = (out / "workspace" / "index.html").read_text(encoding="utf-8")

  assert "<select" not in page, "the rail still offers a select"
  links = {
    label: target
    for target, label in re.findall(
      r'<a class="queue-item[^"]*" href="([^"]+)">([^<]+)</a>', page
    )
  }
  for label in ("Open", "Pending", "Blocked", "Closed"):
    assert label in links, f"the rail answers no {label} link"
    assert (out / links[label] / "index.html").exists(), links[label]
  opened = (out / "workspace" / "status" / "open" / "index.html").read_text(
    encoding="utf-8"
  )
  assert re.search(r'<a class="queue-item is-active" href="[^"]*">Open</a>', opened)


def test_the_client_tabs_lead_to_client_shaped_pages(tmp_path):
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
  home = (out / "home" / "index.html").read_text(encoding="utf-8")
  for head, folder in (("requests", "home/requests"), ("issues", "home/issues")):
    assert f'href="{folder}/"' in home, f"the {head} tab opens the client copy"
    page = (out / folder / "index.html").read_text(encoding="utf-8")
    block = re.search(r'<nav class="tabs".*?</nav>', page, re.DOTALL)
    assert block, f"{folder} carries the tab strip"
    labels = re.findall(r"</svg>([^<]+)</a>", block.group(0))
    assert labels == ["Requests", "Issues"], f"{folder} keeps the client tabs"
  copies = sorted((out / "home" / "requests").glob("*/index.html"))
  assert copies, "a record the client can open gets its own copy"
  record = copies[0].read_text(encoding="utf-8")
  block = re.search(r'<nav class="tabs".*?</nav>', record, re.DOTALL)
  labels = re.findall(r"</svg>([^<]+)</a>", block.group(0)) if block else []
  assert labels == ["Requests", "Issues"], "the record copy keeps the client nav"
  assert re.search(r'href="home/requests/"', record), (
    "the copy points inside the client pages"
  )


def test_the_frozen_switch_links_stay_in_the_frozen_sets(tmp_path):
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
  staff = (out / "workspace" / "index.html").read_text(encoding="utf-8")
  client = (out / "home" / "index.html").read_text(encoding="utf-8")
  assert re.search(r'<a href="[^"]*workspace/" class="on">Staff</a>', staff)
  assert re.search(r'<a href="[^"]*home/">Client</a>', staff)
  assert re.search(r'<a href="[^"]*home/" class="on">Client</a>', client)
  assert re.search(r'<a href="[^"]*workspace/">Staff</a>', client)


def test_a_client_copy_keeps_her_controls_in_the_client_pages(tmp_path):
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
  client = (out / "home").resolve()
  copies = sorted((out / "home" / "requests").glob("*/index.html"))
  assert copies, "a client record copy exists"
  controls = (
    r'<a class="btn" href="([^"]+)">Edit</a>',
    r'<form class="(?:actions|share-form|comment-form)"[^>]*action="([^"]+)"',
  )
  for page in copies:
    html = page.read_text(encoding="utf-8")
    found = [target for pattern in controls for target in re.findall(pattern, html)]
    assert found, f"{page} carries the record controls"
    for target in found:
      path = (out / target.split("?")[0]).resolve()
      assert path == client or client in path.parents, (page, target)


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
    assert len(re.findall(r"<base href=", html)) == 1, page
    for target in LINK_RE.findall(re.sub(r"<base[^>]*>", "", html)):
      if target.startswith(("#", "http", "mailto:", "data:")):
        continue
      assert not target.startswith("/"), (page, target)
      path = out / target.split("?")[0].split("#")[0]
      assert path.exists(), (page, target)


def _frozen_site(tmp_path):
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
  return out


def _page_url(out, page):
  """The address the demo serves one frozen page from, under a subpath."""
  rel = page.parent.relative_to(out).as_posix()
  return SITE + ("" if rel == "." else f"{rel}/")


def test_a_swapped_card_leaves_every_link_on_a_real_page(tmp_path):
  """A card swap leaves the address on a deeper path. No link may depend on that."""
  out = _frozen_site(tmp_path)
  pages = sorted(out.rglob("index.html"))
  urls = [_page_url(out, page) for page in pages]
  prefix = urlparse(SITE).path
  seen = {}

  def exists(path):
    key = path.as_posix()
    if key not in seen:
      seen[key] = path.exists()
    return seen[key]

  for page in pages:
    html = page.read_text(encoding="utf-8")
    base = re.search(r'<base href="([^"]+)"', html)
    pinned = urljoin(_page_url(out, page), base.group(1)) if base else ""
    targets = [
      target
      for target in DEMO_RE.findall(re.sub(r"<base[^>]*>", "", html))
      if not target.startswith(("#", "http", "mailto:", "data:"))
    ]
    for pushed in urls:
      for target in targets:
        landed = urljoin(pinned or pushed, target)
        assert landed.startswith(SITE), (page, pushed, target, landed)
        assert exists(out / urlparse(landed).path[len(prefix) :]), (
          page,
          pushed,
          target,
        )
    assert base, f"{page} answers no base element"
    pin = '<script>document.querySelector("base").href = document.baseURI;</script>'
    assert pin in html, f"{page} leaves its base free to drift"


def test_the_frozen_site_ships_no_service_worker(tmp_path):
  """A worker at the host root cannot install, so the demo must not ask for one."""
  out = _frozen_site(tmp_path)
  script = (out / "static" / "app.js").read_text(encoding="utf-8")

  assert "serviceWorker" not in script
  assert not (out / "sw.js").exists()
  assert not (out / "static" / "sw.js").exists()
