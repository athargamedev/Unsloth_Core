from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ucore_inference_server_help_exposes_serve_and_probe_actions():
    result = subprocess.run(
        [sys.executable, "src/cli/ucore", "inference-server", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "serve" in result.stdout
    assert "status" in result.stdout
    assert "warm" in result.stdout
    assert "judge" in result.stdout
    assert "unload" in result.stdout
