from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_audit_pipeline_plan_uses_target_plan_semantics(tmp_path):
    artifact_index = tmp_path / "artifacts.jsonl"
    audit_out = tmp_path / "audit-plan.json"

    target = subprocess.run(
        [
            sys.executable,
            "src/cli/ucore",
            "target",
            "plan",
            "--npc-key",
            "history_guide",
            "--technique",
            "ollama",
            "--target-stage",
            "train",
            "--artifact-index",
            str(artifact_index),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    audit = subprocess.run(
        [
            sys.executable,
            "src/cli/ucore",
            "audit",
            "pipeline-plan",
            "--npc-key",
            "history_guide",
            "--technique",
            "ollama",
            "--target-stage",
            "train",
            "--artifact-index",
            str(artifact_index),
            "--write",
            str(audit_out),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    target_payload = json.loads(target.stdout)
    audit_payload = json.loads(audit_out.read_text())

    assert target_payload["ready"] == audit_payload["ready"]
    assert [step["stage"] for step in target_payload["steps"]] == [
        step["stage"] for step in audit_payload["steps"]
    ]
    assert "status" in audit_payload["steps"][0]
    assert "action" in audit_payload["steps"][0]
    assert "Pipeline plan written" in audit.stdout
