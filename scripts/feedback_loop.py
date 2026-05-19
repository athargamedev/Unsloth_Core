#!/usr/bin/env python3
"""Compatibility wrapper for the categorized scripts layout."""

from importlib import import_module
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_impl = import_module("scripts.training.feedback_loop")
sys.modules[__name__] = _impl

if __name__ == "__main__" and hasattr(_impl, "main"):
    _impl.main()
