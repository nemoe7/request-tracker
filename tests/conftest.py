import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Repo gates live in `scripts/`, which is not an importable package.
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
