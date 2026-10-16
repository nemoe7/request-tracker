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
  "my",
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


def _relative(target: str, depth: int, frozen: set[str]) -> str:
  """Point one link at the nearest frozen page, relative to the page depth."""
  prefix = "./" if depth == 0 else "../" * depth
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


def rewrite(html: str, depth: int, frozen: set[str]) -> str:
  """Make root-absolute links relative, inside the frozen set, and read-only."""
  prefix = "./" if depth == 0 else "../" * depth
  html = html.replace('"/static/', f'"{prefix}static/')
  html = html.replace('method="post"', 'method="get"')
  return LINK_RE.sub(
    lambda match: f'{match.group(1)}="{_relative(match.group(2), depth, frozen)}"',
    html,
  )


def record_folders(database: Path) -> list[str]:
  """Return one folder per seeded record, so its links have a page to land on."""
  connection = data_db.connect(str(database))
  try:
    return [
      *(f"requests/{record.id}" for record in requests_data.list_requests(connection)),
      *(f"issues/{record.id}" for record in issues_data.list_issues(connection)),
    ]
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
  folders = (*STAFF_PAGES, *record_folders(database))
  frozen = {"", "home", *folders}

  def freeze(route: str, folder: str) -> None:
    response = client.get(route)
    if response.status_code != 200:
      raise SystemExit(f"{route} answered {response.status_code}")
    depth = 0 if not folder else folder.count("/") + 1
    target = out / folder / "index.html" if folder else out / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    page = rewrite(response.get_data(as_text=True), depth, frozen)
    target.write_text(page, encoding="utf-8")
    print(f"froze {route} -> {target.relative_to(out)}")

  freeze("/workspace", "")
  for folder in folders:
    freeze(f"/{folder}", folder)
  client.get("/demo/switch/client")
  freeze("/home", "home")
  shutil.copytree(ROOT / "pwedepa" / "web" / "static", out / "static")
  (out / ".nojekyll").write_text("", encoding="utf-8")
  for leftover in out.glob("demo.db*"):
    leftover.unlink()
  print(f"demo frozen into {out}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
