import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_changelog_names_the_current_version():
  version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
  ]["version"]
  changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
  heading = re.search(rf"^## \[{re.escape(version)}\]", changelog, re.MULTILINE)
  assert heading, f"CHANGELOG.md has no {version} heading"


def test_the_readme_points_at_the_run_notes():
  readme = (ROOT / "README.md").read_text(encoding="utf-8")
  assert "docs/deploy.md" in readme
