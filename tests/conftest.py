import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The repository gates live in scripts/, which is not a package.
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
