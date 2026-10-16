"""Freeze the seeded demo into static pages for GitHub Pages.

GitHub Pages serves files only, so the demo renders once here. The script
seeds a throwaway database, asks the demo app for each page, rewrites the
links to relative paths, and copies the static assets beside the pages.
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


def _relative(target: str, depth: int) -> str:
  prefix = "./" if depth == 0 else "../" * depth
  path = target.split("?", 1)[0].split("#", 1)[0].strip("/")
  if path == "demo/switch/staff":
    return prefix
  if path == "demo/switch/client":
    return prefix + "home/"
  if not path:
    return prefix
  return f"{prefix}{path}/"


def rewrite(html: str, depth: int) -> str:
  """Make root-absolute links relative to the page depth."""
  prefix = "./" if depth == 0 else "../" * depth
  html = html.replace('"/static/', f'"{prefix}static/')
  return LINK_RE.sub(
    lambda match: f'{match.group(1)}="{_relative(match.group(2), depth)}"',
    html,
  )


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

  def freeze(route: str, folder: str) -> None:
    response = client.get(route)
    if response.status_code != 200:
      raise SystemExit(f"{route} answered {response.status_code}")
    depth = 0 if not folder else folder.count("/") + 1
    target = out / folder / "index.html" if folder else out / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rewrite(response.get_data(as_text=True), depth), encoding="utf-8")
    print(f"froze {route} -> {target.relative_to(out)}")

  freeze("/workspace", "")
  for folder in STAFF_PAGES:
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
