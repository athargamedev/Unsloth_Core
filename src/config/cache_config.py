import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = PROJECT_ROOT / "var" / ".cache"
os.environ.setdefault("PYTEST_CACHE_DIR", str(CACHE_DIR / "pytest"))
