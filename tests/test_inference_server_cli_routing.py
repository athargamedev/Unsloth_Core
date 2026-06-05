from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _help(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "src/cli/ucore", *args, "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_generation_and_eval_commands_expose_inference_server_url():
    assert "--inference-server-url" in _help("generate-ollama")
    assert "--inference-server-url" in _help("dataset-eval")
