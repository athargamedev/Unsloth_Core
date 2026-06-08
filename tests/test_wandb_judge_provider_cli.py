from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ucore_exposes_wandb_judge_provider_flags():
    help_by_command = {}
    for command in ["dataset-eval", "evaluate", "feedback", "pipeline"]:
        result = subprocess.run(
            ["./ucore", command, "--help"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        help_by_command[command] = result.stdout

    assert "--judge-provider" in help_by_command["dataset-eval"]
    assert "--wandb-inference-project" in help_by_command["dataset-eval"]
    assert "--judge-provider" in help_by_command["evaluate"]
    assert "--wandb-inference-project" in help_by_command["evaluate"]
    assert "--dataset-eval-judge-provider" in help_by_command["pipeline"]
    assert "--eval-judge-provider" in help_by_command["pipeline"]
    assert "--wandb-inference-project" in help_by_command["pipeline"]

    dataset_help = subprocess.run(
        [sys.executable, "src/cli/ucore", "dataset-eval", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert "--judge-provider" in dataset_help
    assert "--wandb-inference-project" in dataset_help

    feedback_help = subprocess.run(
        [sys.executable, "src/cli/ucore", "feedback", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert feedback_help is not None
