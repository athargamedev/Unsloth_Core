#!/usr/bin/env python3
"""Compatibility wrapper for the categorized scripts layout."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.supabase_integration_check import *  # noqa: F401,F403

if __name__ == "__main__":
    from scripts.ops.supabase_integration_check import main
    main()
