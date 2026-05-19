#!/usr/bin/env python3
"""Compatibility wrapper for the categorized scripts layout."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluation.tb_reader import *  # noqa: F401,F403

if __name__ == "__main__":
    from scripts.evaluation.tb_reader import main
    main()
