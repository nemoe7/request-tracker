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
from pwedepa.data import domains as domains_data
from pwedepa.data import issues as issues_data
from pwedepa.data import requests as requests_data
from pwedepa.web import create_app
from pwedepa.web.routes.demo import set_seat

STAFF_PAGES = (
  "requests",
  "issues",
  "requests/new",
  "notifications",
  "settings",
  "admin",
  "admin/users",
  "admin/shares",
  "admin/audit",
  "admin/config",
)

LINK_RE = re.compile(r'(href|action)="(/(?:[^"]*))"')

# A card swap pushes a deeper address, so the page holds its base at the site root.
BASE_PIN = 'document.querySelector("base").href = document.baseURI;'

STATUS_FORM_RE = re.compile(r'<form class="filter-form".*?</form>', re.DOTALL)
STATUS_OPTION_RE = re.compile(r'<option value="([^"]*)"( selected)?>([^<]*)</option>')
WORKER_BLOCK_RE = re.compile(
  r'(?ms)^[ \t]*if \("serviceWorker" in navigator\) \{.*?^[ \t]*\}\n'
)


VIEW_KEYS = ("selected", "queue", "domain", "visibility", "status")


def _slug(value: str) -> str:
  return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def filter_views(html: str, request_ids: list[int]) -> dict[tuple[str, str], str]:
  """Map each workspace filter and each item row to a folder of its own."""
  views = {
    ("selected", str(number)): f"workspace/record/{number}" for number in request_ids
  }
  for key in VIEW_KEYS[1:]:
    for query in re.findall(r'href="/\?([^"]*)"', html):
      value = dict(parse_qsl(query.replace("&amp;", "&"))).get(key, "")
      if value:
        views[(key, value)] = f"workspace/{key}/{_slug(value)}"
  for value in re.findall(r'<option value="([A-Z]+)"', html):
    views[("status", value)] = f"workspace/status/{_slug(value)}"
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
  frozen: set[str],
  source: str,
  views: dict[tuple[str, str], str],
  nav: dict[str, str] | None = None,
  page: str = "",
) -> str:
  """Point one link at the nearest frozen page, from the site root."""
  if nav:
    path = target.split("?", 1)[0].split("#", 1)[0].strip("/")
    for head, folder in (("requests", "home/requests"), ("issues", "home/issues")):
      if path == head or path.startswith(f"{head}/"):
        tail = folder + path[len(head) :]
        while tail not in frozen and "/" in tail:
          tail = tail.rsplit("/", 1)[0]
        if tail in frozen:
          return f"{tail}/"
    # A client copy links no record page from the staff set.
    match = re.fullmatch(r"[^/]+/(requests|issues)/\d+", path)
    if match and f"home/{match.group(1)}" in frozen:
      return f"home/{match.group(1)}/"
  if "?" in target:
    head, query = target.split("?", 1)
    if not head.strip("/"):
      folder = _view(query, source, views)
      if folder:
        return f"{folder}/"
  path = target.split("?", 1)[0].split("#", 1)[0].strip("/")
  while path not in frozen:
    if "/" not in path:
      return f"{page}/" if page else "./"
    path = path.rsplit("/", 1)[0]
  return "./" if not path else f"{path}/"


def _status_list(html: str, frozen, source: str, views, page: str) -> str:
  """Swap the status form for one link per status, so a file host serves it."""
  form = STATUS_FORM_RE.search(html)
  if not form:
    return html
  links = []
  for value, selected, label in STATUS_OPTION_RE.findall(form.group(0)):
    target = _relative(f"/?status={value}", frozen, source, views, None, page)
    mark = " is-active" if selected else ""
    links.append(f'<a class="queue-item{mark}" href="{target}">{label}</a>')
  return f"{html[: form.start()]}{''.join(links)}{html[form.end() :]}"


def rewrite(
  html: str, prefix: str, frozen: set[str], source: str, views, nav=None, page=""
) -> str:
  """Point every link at the frozen site root, and open the demo read-only."""
  own = f"{page}/" if page else "./"
  html = html.replace('"/static/', '"static/')
  html = html.replace('method="post"', 'method="get"')
  # A frozen page has no account behind it, so its theme stays a browser choice.
  html = html.replace('data-theme-scope="account"', 'data-theme-scope="browser"')
  html = html.replace(
    '<meta charset="utf-8">',
    f'<meta charset="utf-8">\n  <base href="{prefix}">\n  <script>{BASE_PIN}</script>',
    1,
  )
  html = re.sub(
    r'href="#([^"]*)"', lambda match: f'href="{own}#{match.group(1)}"', html
  )
  html = _status_list(html, frozen, source, views, page)
  return LINK_RE.sub(
    lambda match: (
      f'{match.group(1)}="{_relative(match.group(2), frozen, source, views, nav, page)}"'
    ),
    html,
  )


def missing_scripts(source: Path, static: Path) -> list[str]:
  """Return the scripts the copy left behind, the top worker file aside."""
  expected = {
    path.relative_to(source)
    for path in source.rglob("*.js")
    if path.relative_to(source) != Path("sw.js")
  }
  copied = {path.relative_to(static) for path in static.rglob("*.js")}
  return sorted(str(path) for path in expected - copied)


def copy_static(static: Path, source: Path | None = None) -> None:
  """Copy the app files, keep only the top worker out, and name a lost script."""
  source = source or ROOT / "pwedepa" / "web" / "static"
  shutil.copytree(
    source,
    static,
    ignore=lambda folder, names: (
      ["sw.js"] if Path(folder) == source and "sw.js" in names else []
    ),
  )
  lost = missing_scripts(source, static)
  if lost:
    raise SystemExit(f"the frozen site lost {', '.join(lost)}")


def keep_workers_out(static: Path) -> None:
  """Take the worker out of every copied script, and refuse a leftover."""
  for script in sorted(static.rglob("*.js")):
    source = script.read_text(encoding="utf-8")
    kept = WORKER_BLOCK_RE.sub("", source, count=1)
    if kept != source:
      script.write_text(kept, encoding="utf-8")
    if "serviceWorker" in kept:
      raise SystemExit(f"{script.name} still names a service worker")
    if kept.count("{") != kept.count("}"):
      raise SystemExit(f"{script.name} lost a brace with the worker block")


def seeded_records(database: Path):
  """Return the seeded requests and issues, so their links have a page."""
  connection = data_db.connect(str(database))
  try:
    return (
      requests_data.list_requests(connection),
      issues_data.list_issues(connection),
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
      "DEMO_SWITCH": True,
      "SESSION_COOKIE_SECURE": False,
      "WEBAUTHN_RP_ID": "nemoe7.github.io",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://nemoe7.github.io",
    }
  )
  client = app.test_client()
  found = domains_data.load(database)
  request_rows, issue_rows = seeded_records(database)
  request_ids = [record.id for record in request_rows]
  views = filter_views(client.get("/").get_data(as_text=True), request_ids)

  def record_folder(record, kind: str) -> str:
    return f"{domains_data.slug_for(record.domains, found)}/{kind}/{record.id}"

  record_folders = [
    *(record_folder(record, "requests") for record in request_rows),
    *(record_folder(record, "issues") for record in issue_rows),
  ]
  folders = (
    *STAFF_PAGES,
    *(domain.slug for domain in found),
    *record_folders,
  )
  frozen = {"", "home", *folders, *views.values()}

  def freeze(route: str, folder: str, source: str = "", nav=None) -> None:
    response = client.get(route)
    if response.status_code != 200:
      raise SystemExit(f"{route} answered {response.status_code}")
    prefix = "./" if not folder else "../" * (folder.count("/") + 1)
    target = out / folder / "index.html" if folder else out / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    html = rewrite(
      response.get_data(as_text=True), prefix, frozen, source, views, nav, folder
    )
    target.write_text(html, encoding="utf-8")
    print(f"froze {route} -> {target.relative_to(out)}")

  freeze("/", "")
  for folder in folders:
    freeze(f"/{folder}", folder)
  for (key, value), folder in views.items():
    freeze(f"/?{key}={value}", folder, source=f"{key}={value}")
  set_seat("client")
  nav = {"requests": "home/requests", "issues": "home/issues"}
  client_pages = [("/requests", "home")]
  for head, folder in (("requests", "home/requests"), ("issues", "home/issues")):
    listing = client.get(f"/{head}").get_data(as_text=True)
    client_pages.append((f"/{head}", folder))
    routes = sorted(
      set(re.findall(r'href="(/[^"]*/(?:requests|issues)/\d+)"', listing))
    )
    for route in routes:
      kind = "requests" if "/requests/" in route else "issues"
      target = f"home/{kind}/{route.rsplit('/', 1)[1]}"
      nav[route.strip("/")] = target
      client_pages.append((route, target))
  frozen.update(folder for _, folder in client_pages)
  for route, folder in client_pages:
    freeze(route, folder, nav=nav)
  static = out / "static"
  copy_static(static)
  if (static / "sw.js").exists():
    raise SystemExit("the frozen site still carries a worker")
  keep_workers_out(static)
  (out / ".nojekyll").write_text("", encoding="utf-8")
  for leftover in out.glob("demo.db*"):
    leftover.unlink()
  print(f"demo frozen into {out}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
