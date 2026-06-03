from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.core.ops.npc_production_strategy import (
    classify_feedback_cycle,
    density_repair_needed,
    load_strategy_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_production_profile_carries_shared_pipeline_defaults():
    profile = load_strategy_profile("npc-production-grounded")

    assert profile["technique"] == "ollama"
    assert profile["dataset"]["target_total_rows"] >= 120
    assert profile["dataset"]["density"]["teaching"]["min_words"] == 35
    assert profile["quality_gate"]["mode"] == "release"
    assert profile["quality_gate"]["judge_provider"] == "wandb"
    assert profile["quality_gate"]["confident"] is True
    assert profile["training"]["export_gguf"] is True
    assert profile["runtime_eval"]["requires_base_model"] is True


def test_density_repair_detects_terse_candidate_even_after_gate():
    feedback = {
        "win_rate": 0.29,
        "avg_candidate_words": 24,
        "avg_baseline_words": 51,
        "weak_concepts": ["teaching/overview"],
    }

    decision = density_repair_needed(feedback)

    assert decision["needed"] is True
    assert decision["reason"] == "candidate_too_terse"
    assert decision["target_min_words"] == 35
    assert decision["target_max_words"] == 55


def test_feedback_cycle_escalates_after_bounded_repairs():
    feedback = {
        "npc_key": "marvel_heroes_instructor",
        "repair_history": [
            {"class": "exact_confident_failure"},
            {"class": "density_repair"},
            {"class": "training_preset_variant"},
        ],
    }

    decision = classify_feedback_cycle(feedback)

    assert decision["action"] == "escalate_shared_strategy"
    assert "stop_per_npc_loop" in decision["flags"]


def test_ucore_strategy_command_exposes_profile_summary():
    result = subprocess.run(
        [sys.executable, "./ucore", "strategy", "--profile", "npc-production-grounded", "--json"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "npc-production-grounded" in result.stdout
    assert "quality_gate" in result.stdout
    assert "runtime_eval" in result.stdout
