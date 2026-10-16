"""Freeze the seeded demo into static pages for GitHub Pages.

GitHub Pages serves files only, so the demo renders once here. The script
seeds a throwaway database and asks the demo app for each page. It then
rewrites the links to relative paths, points every link at a frozen page, and
turns the write forms into plain reads.
"""

import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qsl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_seed import seed_file

from pwedepa.data import db as data_db
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.web import create_app

STAFF_PAGES = (
  "workspace",
  "requests",
  "issues",
  "issues/1",
  "issues/2",
  "requests/1",
  "requests/5",
  "requests/new",
  "notifications",
  "settings",
  "admin",
  "admin/users",
  "admin/shares",
  "admin/audit",
)

LINK_RE = re.compile(r'(href|action)="(/(?:[^"]*))"')


VIEW_KEYS = ("selected", "queue", "domain", "visibility")


def _slug(value: str) -> str:
  return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def filter_views(html: str, request_ids: list[int]) -> dict[tuple[str, str], str]:
  """Map each workspace filter and record row to a folder of its own."""
  views = {
    ("selected", str(number)): f"workspace/record/{number}" for number in request_ids
  }
  for key in VIEW_KEYS[1:]:
    for query in re.findall(r'href="/workspace\?([^"]*)"', html):
      value = dict(parse_qsl(query.replace("&amp;", "&"))).get(key, "")
      if value:
        views[(key, value)] = f"workspace/{key}/{_slug(value)}"
  return views


def _view(query: str, source: str, views: dict[tuple[str, str], str]) -> str | None:
  """Return the frozen page for the first filter a link changes."""
  new = dict(parse_qsl(query.replace("&amp;", "&")))
  old = dict(parse_qsl(source.replace("&amp;", "&")))
  old.setdefault("queue", "triage")
  for key in VIEW_KEYS:
    value = new.get(key, "")
    if value and value != old.get(key, ""):
      folder = views.get((key, value))
      if folder:
        return folder
  return None


def _relative(
  target: str,
  depth: int,
  frozen: set[str],
  source: str,
  views: dict[tuple[str, str], str],
  nav: dict[str, str] | None = None,
) -> str:
  """Point one link at the nearest frozen page, relative to the page depth."""
  prefix = "./" if depth == 0 else "../" * depth
  if nav:
    path = target.split("?", 1)[0].split("#", 1)[0].strip("/")
    for head, folder in nav.items():
      if path == head or path.startswith(f"{head}/"):
        tail = folder + path[len(head) :]
        if tail in frozen:
          return f"{prefix}{tail}/"
  if "?" in target:
    head, query = target.split("?", 1)
    if head.strip("/") == "workspace":
      folder = _view(query, source, views)
      if folder:
        return f"{prefix}{folder}/"
  path = target.split("?", 1)[0].split("#", 1)[0].strip("/")
  if path == "demo/switch/staff":
    return prefix
  if path == "demo/switch/client":
    return prefix + "home/"
  while path not in frozen:
    if "/" not in path:
      return prefix
    path = path.rsplit("/", 1)[0]
  return prefix if not path else f"{prefix}{path}/"


def rewrite(
  html: str, depth: int, frozen: set[str], source: str, views, nav=None
) -> str:
  """Make root-absolute links relative, inside the frozen set, and read-only."""
  prefix = "./" if depth == 0 else "../" * depth
  html = html.replace('"/static/', f'"{prefix}static/')
  html = html.replace('method="post"', 'method="get"')
  return LINK_RE.sub(
    lambda match: (
      f'{match.group(1)}="{_relative(match.group(2), depth, frozen, source, views, nav)}"'
    ),
    html,
  )


def seeded_records(database: Path) -> tuple[list[int], list[int]]:
  """Return the seeded request and issue ids, so their links have a page."""
  connection = data_db.connect(str(database))
  try:
    return (
      [record.id for record in requests_data.list_requests(connection)],
      [record.id for record in issues_data.list_issues(connection)],
    )
  finally:
    connection.close()


def main() -> int:
  out = Path(os.environ.get("PWEDEPA_PAGES_OUT", ROOT / "_site"))
  if out.exists():
    shutil.rmtree(out)
  out.mkdir(parents=True)
  database = out / "demo.db"
  seed_file(database)
  app = create_app(
    {
      "DATABASE": str(database),
      "DEMO_MODE": True,
      "SESSION_COOKIE_SECURE": False,
      "WEBAUTHN_RP_ID": "nemoe7.github.io",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://nemoe7.github.io",
    }
  )
  client = app.test_client()
  request_ids, issue_ids = seeded_records(database)
  views = filter_views(client.get("/workspace").get_data(as_text=True), request_ids)
  folders = (
    *STAFF_PAGES,
    *(f"requests/{number}" for number in request_ids),
    *(f"issues/{number}" for number in issue_ids),
  )
  frozen = {"", "home", *folders, *views.values()}

  def freeze(route: str, folder: str, source: str = "", nav=None) -> None:
    response = client.get(route)
    if response.status_code != 200:
      raise SystemExit(f"{route} answered {response.status_code}")
    depth = 0 if not folder else folder.count("/") + 1
    target = out / folder / "index.html" if folder else out / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    page = rewrite(response.get_data(as_text=True), depth, frozen, source, views, nav)
    target.write_text(page, encoding="utf-8")
    print(f"froze {route} -> {target.relative_to(out)}")

  freeze("/workspace", "")
  for folder in folders:
    freeze(f"/{folder}", folder)
  for (key, value), folder in views.items():
    freeze(f"/workspace?{key}={value}", folder, source=f"{key}={value}")
  client.get("/demo/switch/client")
  nav = {"requests": "home/requests", "issues": "home/issues"}
  client_pages = [("/home", "home")]
  for head, folder in nav.items():
    listing = client.get(f"/{head}").get_data(as_text=True)
    client_pages.append((f"/{head}", folder))
    numbers = sorted(set(re.findall(rf'href="/{head}/(\d+)"', listing)))
    client_pages += [(f"/{head}/{number}", f"{folder}/{number}") for number in numbers]
  frozen.update(folder for _, folder in client_pages)
  for route, folder in client_pages:
    freeze(route, folder, nav=nav)
  shutil.copytree(ROOT / "pwedepa" / "web" / "static", out / "static")
  (out / ".nojekyll").write_text("", encoding="utf-8")
  for leftover in out.glob("demo.db*"):
    leftover.unlink()
  print(f"demo frozen into {out}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
