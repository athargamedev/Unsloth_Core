from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ucore_sanitize_exposes_judge_cache_controls():
    result = subprocess.run(
        [sys.executable, "src/cli/ucore", "sanitize", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--judge-cache-path" in result.stdout
    assert "--no-judge-cache" in result.stdout
    assert "--inference-server-url" in result.stdout


def test_sanitize_module_exposes_judge_cache_controls():
    result = subprocess.run(
        [sys.executable, "src/core/dataset/sanitize_dataset.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "--judge-cache-path" in result.stdout
    assert "--no-judge-cache" in result.stdout
    assert "--inference-server-url" in result.stdout
