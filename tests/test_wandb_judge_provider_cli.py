from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ucore_exposes_wandb_judge_provider_flags():
    for command in ["dataset-eval", "evaluate", "feedback"]:
        result = subprocess.run(
            [sys.executable, "./ucore", command, "--help"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        assert "judge-provider" in result.stdout

    dataset_help = subprocess.run(
        [sys.executable, "scripts/dataset/dataset_eval.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert "--judge-provider" in dataset_help
    assert "--wandb-inference-project" in dataset_help
