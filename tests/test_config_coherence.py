from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_config_coherence_current_project_is_green():
    from src.core.ops.config_coherence import audit_config_coherence

    result = audit_config_coherence(PROJECT_ROOT)

    assert result["ok"], json.dumps(result, indent=2)
    assert result["failures"] == []


def test_config_coherence_flags_template_production_profile(tmp_path):
    from src.core.ops.config_coherence import audit_config_coherence

    etc = tmp_path / "etc"
    presets = etc / "presets"
    eval_dir = tmp_path / "src" / "core" / "evaluation"
    presets.mkdir(parents=True)
    eval_dir.mkdir(parents=True)
    (etc / "npc-production-strategy.yaml").write_text(
        yaml.safe_dump(
            {
                "profiles": {
                    "npc-production-bad": {
                        "technique": "template",
                        "dataset": {"template_allowed": True},
                        "training": {
                            "lora_r": 16,
                            "lora_alpha": 32,
                            "packing": True,
                            "train_on_responses_only": False,
                        },
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (etc / "parameter-registry.yaml").write_text(
        "parameters:\n  lora_alpha:\n    tooltip: 'Usually 2x lora_r'\n",
        encoding="utf-8",
    )
    (presets / "fast-3b.yaml").write_text(
        "training:\n  train_on_responses_only: false\nlora:\n  r: 16\n  alpha: 32\n",
        encoding="utf-8",
    )
    (eval_dir / "quick_eval.py").write_text("lora_alpha=32\n", encoding="utf-8")

    result = audit_config_coherence(tmp_path)

    reasons = {failure["reason"] for failure in result["failures"]}
    assert result["ok"] is False
    assert "production profile cannot use smoke-only template technique" in reasons
    assert "production profile must not allow template datasets" in reasons
    assert "production LoRA alpha must equal rank unless experimental" in reasons
    assert "production training must use response-only masking" in reasons
    assert "6GB-safe production training must disable packing" in reasons
    assert "parameter registry must not describe alpha=2r as normal production policy" in reasons
    assert "hardcoded lora_alpha=32 must be smoke-only, experimental, or config-driven" in reasons


def test_ucore_audit_config_coherence_json_is_green():
    result = subprocess.run(
        [sys.executable, "./ucore", "audit", "config-coherence", "--json"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True, json.dumps(payload, indent=2)
    assert payload["failures"] == []
