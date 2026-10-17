"""PwedePa: self-hosted issue and request tracker."""

import subprocess
from functools import lru_cache
from pathlib import Path

__version__ = "0.1.0"

# The image build writes this file; a checkout has no such file.
STAMP = Path(__file__).with_name("_version.txt")


@lru_cache(maxsize=1)
def build_label() -> str:
  """Name the build: the short hash, the release tag, or the version."""
  if STAMP.is_file():
    stamped = STAMP.read_text(encoding="utf-8").strip()
    if stamped:
      # The CI image is stamped `dev-<hash>`; the header shows the hash alone.
      return stamped.removeprefix("dev-")
  root = Path(__file__).resolve().parent.parent
  if (root / ".git").exists():
    try:
      result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short=7", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
      )
    except OSError:
      return f"v{__version__}"
    if result.returncode == 0 and result.stdout.strip():
      return result.stdout.strip()
  return f"v{__version__}"
