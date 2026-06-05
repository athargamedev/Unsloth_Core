"""P6 experiment registry + comparison unification contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_experiment_run_has_canonical_identity_and_provenance_fields(tmp_path):
    from src.core.ops.experiment_registry import ExperimentRun

    run = ExperimentRun(
        run_id="run_001",
        npc_key="chef_assistant",
        stage="evaluate",
        technique="ollama",
        status="complete",
        profile="npc-production-grounded",
        dataset_hash="abc123",
        model_name="chef_assistant_qwen_lora_r16",
        metrics={"win_rate": 0.72, "quality_pass_rate": 0.91},
        artifacts={"report": "reports/eval.html"},
        external_refs={"wandb_run_id": "wandb-1", "confident_trace_id": "trace-1"},
    )

    data = run.to_record()
    for key in (
        "run_id",
        "npc_key",
        "stage",
        "technique",
        "status",
        "profile",
        "dataset_hash",
        "model_name",
        "metrics",
        "artifacts",
        "external_refs",
        "created_at",
        "schema_version",
    ):
        assert key in data
    assert data["schema_version"] == "experiment_run/v1"
    assert data["metrics"]["win_rate"] == 0.72


def test_experiment_registry_appends_and_queries_jsonl(tmp_path):
    from src.core.ops.experiment_registry import ExperimentRegistry, ExperimentRun

    registry_path = tmp_path / "experiments.jsonl"
    registry = ExperimentRegistry(registry_path)
    registry.record_run(
        ExperimentRun(
            run_id="run_a",
            npc_key="chef_assistant",
            stage="train",
            technique="ollama",
            status="complete",
            metrics={"loss": 0.2},
        )
    )
    registry.record_run(
        ExperimentRun(
            run_id="run_b",
            npc_key="history_guide",
            stage="evaluate",
            technique="docs",
            status="failed",
        )
    )

    assert registry_path.exists()
    rows = _read_jsonl(registry_path)
    assert [r["run_id"] for r in rows] == ["run_a", "run_b"]
    assert [r["run_id"] for r in registry.query_runs(npc_key="chef_assistant")] == ["run_a"]
    assert [r["run_id"] for r in registry.query_runs(stage="evaluate")] == ["run_b"]


def test_workflow_hook_recorder_records_experiment_run_on_terminal_event(tmp_path, monkeypatch):
    from src.core.ops.workflow_hooks import WorkflowHookRecorder

    hook_path = tmp_path / "hooks.jsonl"
    exp_path = tmp_path / "experiments.jsonl"
    monkeypatch.setenv("EXPERIMENT_REGISTRY_PATH", str(exp_path))

    recorder = WorkflowHookRecorder(
        hook_path,
        tool="ucore",
        npc_key="chef_assistant",
        technique="ollama",
        run_id="run_hook",
        db=None,
    )
    recorder.emit(
        "training_pipeline",
        "complete",
        profile="npc-production-grounded",
        output_dir="outputs/train/run_hook",
        model_name="chef_lora",
        metrics={"loss": 0.12},
        wandb_run_id="wb-123",
        confident_trace_id="ct-123",
    )

    hook_rows = _read_jsonl(hook_path)
    exp_rows = _read_jsonl(exp_path)
    assert hook_rows[0]["status"] == "complete"
    assert exp_rows[0]["run_id"] == "run_hook"
    assert exp_rows[0]["stage"] == "training_pipeline"
    assert exp_rows[0]["metrics"]["loss"] == 0.12
    assert exp_rows[0]["external_refs"] == {
        "wandb_run_id": "wb-123",
        "confident_trace_id": "ct-123",
    }


def test_compare_canonical_runs_records_comparison_in_experiment_registry(tmp_path, monkeypatch):
    from src.core.ops.compare_canonical_runs import compare_and_record

    runs_root = tmp_path / "runs"
    comparisons_root = tmp_path / "comparisons"
    registry_path = tmp_path / "experiments.jsonl"
    for run_id, score in (("baseline", 0.5), ("candidate", 0.8)):
        bundle_dir = runs_root / run_id
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "artifacts.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "npc_key": "chef_assistant",
                    "stage": "evaluate",
                    "technique": "ollama",
                    "metrics": {"pass_rate": score},
                    "artifacts": {"report": f"{run_id}.html"},
                }
            ),
            encoding="utf-8",
        )

    report_path, comparison = compare_and_record(
        "baseline",
        "candidate",
        runs_root=runs_root,
        comparisons_root=comparisons_root,
        registry_path=registry_path,
    )

    assert report_path.exists()
    assert comparison.winner == "candidate"
    records = _read_jsonl(registry_path)
    assert len(records) == 1
    assert records[0]["stage"] == "compare"
    assert records[0]["status"] == "complete"
    assert records[0]["comparison"]["winner"] == "candidate"
    assert records[0]["comparison"]["baseline_run_id"] == "baseline"
    assert records[0]["comparison"]["candidate_run_id"] == "candidate"


def test_promote_uses_latest_comparison_record_not_latest_pointer_guesswork(tmp_path):
    from src.core.ops.experiment_registry import ExperimentRegistry, ExperimentRun
    from src.core.ops.promote_model import promotion_decision

    registry_path = tmp_path / "experiments.jsonl"
    registry = ExperimentRegistry(registry_path)
    registry.record_run(
        ExperimentRun(
            run_id="cmp_old",
            npc_key="chef_assistant",
            stage="compare",
            technique="ollama",
            status="complete",
            comparison={
                "baseline_run_id": "base",
                "candidate_run_id": "cand_old",
                "winner": "baseline",
                "metrics_delta": {"delta": -0.1},
            },
        )
    )
    registry.record_run(
        ExperimentRun(
            run_id="cmp_new",
            npc_key="chef_assistant",
            stage="compare",
            technique="ollama",
            status="complete",
            comparison={
                "baseline_run_id": "base",
                "candidate_run_id": "cand_new",
                "winner": "candidate",
                "metrics_delta": {"delta": 0.3},
            },
        )
    )

    decision = promotion_decision(
        npc_key="chef_assistant",
        candidate_run_id="cand_new",
        registry_path=registry_path,
        dry_run=True,
    )
    assert decision["can_promote"] is True
    assert decision["candidate_run_id"] == "cand_new"
    assert decision["source_comparison_run_id"] == "cmp_new"
    assert decision["dry_run"] is True


def test_cli_promote_dry_run_outputs_json_from_comparison_registry(tmp_path):
    from src.core.ops.experiment_registry import ExperimentRegistry, ExperimentRun

    registry_path = tmp_path / "experiments.jsonl"
    ExperimentRegistry(registry_path).record_run(
        ExperimentRun(
            run_id="cmp_cli",
            npc_key="chef_assistant",
            stage="compare",
            technique="ollama",
            status="complete",
            comparison={
                "baseline_run_id": "base",
                "candidate_run_id": "cand_cli",
                "winner": "candidate",
                "metrics_delta": {"delta": 0.25},
            },
        )
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "src" / "cli" / "ucore"),
            "promote",
            "--npc-key",
            "chef_assistant",
            "--candidate-run-id",
            "cand_cli",
            "--registry-path",
            str(registry_path),
            "--dry-run",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["can_promote"] is True
    assert data["candidate_run_id"] == "cand_cli"
    assert data["dry_run"] is True
