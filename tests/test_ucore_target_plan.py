from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ucore_target_plan_outputs_cache_aware_json(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "./ucore",
            "target",
            "plan",
            "--npc-key",
            "chef_assistant",
            "--technique",
            "ollama",
            "--target-stage",
            "sanitize",
            "--artifact-index",
            str(tmp_path / "artifacts.jsonl"),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_stage"] == "sanitize"
    assert payload["ready"] is False
    assert [step["stage"] for step in payload["steps"]] == ["generate", "sanitize"]
    assert payload["steps"][0]["status"] == "missing"
    assert payload["steps"][0]["action"] == "run"
    assert payload["run_spec"]["generation"]["command"] == "generate-ollama"
    assert payload["run_spec"]["dataset_eval"]["judge_provider"] == "wandb"
    assert payload["run_spec"]["training"]["train_on_responses_only"] is True
    assert payload["run_spec"]["runtime_eval"]["requires_base_model"] is True
    assert "integrations" in payload["run_spec"]
    assert "dry_run_commands" in payload


def test_ucore_target_plan_table_mentions_next_action(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "./ucore",
            "target",
            "plan",
            "--npc-key",
            "chef_assistant",
            "--technique",
            "ollama",
            "--target-stage",
            "sanitize",
            "--artifact-index",
            str(tmp_path / "artifacts.jsonl"),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    out = result.stdout.lower()
    assert "target plan" in out
    assert "generate" in out
    assert "missing" in out
    assert "run" in out
