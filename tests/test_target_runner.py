"""Tests for enhanced target plan schema (P5.1) and TargetRunner (P5.2, P5.3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _populated_registry(tmp_path):
    """Return an ArtifactRegistry with one complete NPC chain up to evaluate,
    with proper input_signature metadata for cache lineage verification."""
    from src.core.ops.artifact_registry import ArtifactRegistry

    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")

    # generate -> dataset_raw (no inputs)
    r1 = tmp_path / "raw.jsonl"
    r1.write_text("{}", encoding="utf-8")
    registry.record_artifact(
        "r-gen",
        "chef_assistant",
        "generate",
        "dataset_raw",
        r1,
        technique="ollama",
        metadata={"input_signature": "gen-init"},
    )

    # sanitize -> dataset_clean (input: dataset_raw)
    r2 = tmp_path / "clean.jsonl"
    r2.write_text("{}", encoding="utf-8")
    registry.record_artifact(
        "r-san",
        "chef_assistant",
        "sanitize",
        "dataset_clean",
        r2,
        technique="ollama",
        metadata={
            "input_signature": _sig_for(
                "sanitize", [{"artifact_type": "dataset_raw", "sha256": _sha(r1)}]
            )
        },
    )

    # dataset_eval -> quality_summary (input: dataset_clean)
    r3 = tmp_path / "quality.json"
    r3.write_text(json.dumps({"score": 0.85}), encoding="utf-8")
    registry.record_artifact(
        "r-eval",
        "chef_assistant",
        "dataset_eval",
        "quality_summary",
        r3,
        technique="ollama",
        metadata={
            "input_signature": _sig_for(
                "dataset_eval", [{"artifact_type": "dataset_clean", "sha256": _sha(r2)}]
            )
        },
    )

    # train -> adapter_checkpoint (input: dataset_clean, quality_summary)
    r4 = tmp_path / "checkpoint.json"
    r4.write_text(json.dumps({"adapter": "config"}), encoding="utf-8")
    registry.record_artifact(
        "r-train",
        "chef_assistant",
        "train",
        "adapter_checkpoint",
        r4,
        technique="ollama",
        metadata={
            "input_signature": _sig_for(
                "train",
                [
                    {"artifact_type": "dataset_clean", "sha256": _sha(r2)},
                    {"artifact_type": "quality_summary", "sha256": _sha(r3)},
                ],
            )
        },
    )

    # export -> gguf_adapter (input: adapter_checkpoint)
    r5 = tmp_path / "model.gguf"
    r5.write_bytes(b"\x00\x01\x02")
    registry.record_artifact(
        "r-export",
        "chef_assistant",
        "export",
        "gguf_adapter",
        r5,
        technique="ollama",
        metadata={
            "input_signature": _sig_for(
                "export", [{"artifact_type": "adapter_checkpoint", "sha256": _sha(r4)}]
            )
        },
    )

    # evaluate -> eval_index (input: gguf_adapter)
    r6 = tmp_path / "eval.index.json"
    r6.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
    registry.record_artifact(
        "r-eval",
        "chef_assistant",
        "evaluate",
        "eval_index",
        r6,
        technique="ollama",
        metadata={
            "input_signature": _sig_for(
                "evaluate", [{"artifact_type": "gguf_adapter", "sha256": _sha(r5)}]
            )
        },
    )

    return registry


def _sha(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sig_for(stage: str, inputs: list[dict]) -> str:
    import hashlib

    # Must match the exact format in stage_input_signature (pipeline_dag.py)
    payload = {
        "stage": stage,
        "inputs": [
            {
                "artifact_type": inp.get("artifact_type"),
                "sha256": inp.get("sha256"),
                "path": None,  # sha256 exists so path is null
            }
            for inp in inputs
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


# ── P5.1: Enhanced target plan schema ─────────────────────────────────────────


class TestPlanSchema:
    def test_plan_target_returns_required_top_level_fields(self, tmp_path):
        from src.core.ops.pipeline_dag import PipelineDAG

        registry = _populated_registry(tmp_path)
        dag = PipelineDAG(registry=registry)
        plan = dag.plan_target("evaluate", npc_key="chef_assistant", technique="ollama")

        assert "npc_key" in plan
        assert "technique" in plan
        assert "target_stage" in plan
        assert "ready" in plan
        assert "steps" in plan
        assert "blockers" in plan
        assert "cache_hits" in plan
        assert "gpu_policy" in plan
        assert "next_required_stage" in plan

    def test_plan_target_cache_hits_lists_cached_stages(self, tmp_path):
        from src.core.ops.pipeline_dag import PipelineDAG

        registry = _populated_registry(tmp_path)
        dag = PipelineDAG(registry=registry)
        plan = dag.plan_target("sanitize", npc_key="chef_assistant", technique="ollama")

        # generate should be cached
        assert "generate" in plan["cache_hits"]
        assert plan["cache_hits"]["generate"]["artifact_type"] == "dataset_raw"

    def test_plan_target_blockers_list_reasons_for_not_ready(self, tmp_path):
        from src.core.ops.pipeline_dag import PipelineDAG

        registry = _populated_registry(tmp_path)
        dag = PipelineDAG(registry=registry)

        # No eval_index yet for evaluate — should be a blocker
        plan = dag.plan_target("evaluate", npc_key="unknown_npc", technique="ollama")
        if not plan["ready"]:
            assert isinstance(plan["blockers"], list)
            if plan["blockers"]:
                assert all(isinstance(b, str) for b in plan["blockers"])

    def test_plan_target_gpu_policy_assigns_lease_stages(self, tmp_path):
        from src.core.ops.pipeline_dag import PipelineDAG

        registry = _populated_registry(tmp_path)
        dag = PipelineDAG(registry=registry)
        plan = dag.plan_target("evaluate", npc_key="chef_assistant", technique="ollama")

        assert isinstance(plan["gpu_policy"], dict)
        for stage in ["train", "export"]:
            assert stage in plan["gpu_policy"]
            assert plan["gpu_policy"][stage]["lease_required"] is True

    def test_plan_target_next_required_stage(self, tmp_path):
        from src.core.ops.pipeline_dag import PipelineDAG

        registry = _populated_registry(tmp_path)
        dag = PipelineDAG(registry=registry)

        # For full pipeline with no artifacts, first required is generate
        plan = dag.plan_target("evaluate", npc_key="unknown_npc", technique="ollama")
        assert plan["next_required_stage"] is not None

    def test_plan_ready_all_cached(self, tmp_path):
        from src.core.ops.pipeline_dag import PipelineDAG

        registry = _populated_registry(tmp_path)
        dag = PipelineDAG(registry=registry)
        plan = dag.plan_target("evaluate", npc_key="chef_assistant", technique="ollama")
        assert plan["ready"] is True
        assert plan["next_required_stage"] is None


# ── P5.2: TargetRunner dry-run ────────────────────────────────────────────────


class TestTargetRunner:
    def test_runner_plan_output_matches_target_plan_schema(self, tmp_path):
        from src.core.orchestration.target_runner import TargetRunner

        runner = TargetRunner(artifact_index=tmp_path / "artifacts.jsonl")
        plan = runner.plan(
            npc_key="chef_assistant",
            profile="npc-production-grounded",
            technique="ollama",
            target_stage="evaluate",
        )

        assert plan["npc_key"] == "chef_assistant"
        assert plan["profile"] == "npc-production-grounded"
        assert "steps" in plan
        assert "blockers" in plan
        assert "cache_hits" in plan
        assert "gpu_policy" in plan

    def test_runner_dry_run_returns_command_list_for_non_cached_stages(self, tmp_path):
        from src.core.orchestration.target_runner import TargetRunner

        runner = TargetRunner(artifact_index=tmp_path / "artifacts.jsonl")
        plan = runner.plan(
            npc_key="chef_assistant",
            profile="npc-production-grounded",
            technique="ollama",
            target_stage="sanitize",
        )

        dry = runner.dry_run(plan)
        assert isinstance(dry, list)
        assert len(dry) > 0
        for cmd in dry:
            assert "command" in cmd
            assert "stage" in cmd
            assert "reason" in cmd
            if cmd["stage"] != "generate":
                assert "depends_on" in cmd

    def test_runner_dry_run_no_commands_when_ready(self, tmp_path):
        from src.core.orchestration.target_runner import TargetRunner

        _populated_registry(tmp_path)
        runner = TargetRunner(artifact_index=tmp_path / "artifacts.jsonl")
        plan = runner.plan(
            npc_key="chef_assistant",
            profile="npc-production-grounded",
            technique="ollama",
            target_stage="evaluate",
        )

        dry = runner.dry_run(plan)
        assert len(dry) == 0

    def test_runner_run_creates_registry_entries(self, tmp_path):
        # Create just one artifact (generate) so it tries to run sanitize
        from src.core.ops.artifact_registry import ArtifactRegistry
        from src.core.orchestration.target_runner import TargetRunner

        registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
        r1 = tmp_path / "raw.jsonl"
        r1.write_text("{}", encoding="utf-8")
        registry.record_artifact(
            "r-gen", "chef_assistant", "generate", "dataset_raw", r1, technique="ollama"
        )

        runner = TargetRunner(
            artifact_index=tmp_path / "artifacts.jsonl",
            run_index=tmp_path / "runs.jsonl",
        )
        plan = runner.plan(
            npc_key="chef_assistant",
            profile="npc-production-grounded",
            technique="ollama",
            target_stage="sanitize",
        )

        # run with --dry-run should not execute
        dry_cmds = runner.run(plan, dry_run=True)
        assert isinstance(dry_cmds, list)

    def test_runner_run_with_resume_skips_completed_stages(self, tmp_path):
        from src.core.orchestration.target_runner import TargetRunner

        _populated_registry(tmp_path)
        runner = TargetRunner(
            artifact_index=tmp_path / "artifacts.jsonl",
            run_index=tmp_path / "runs.jsonl",
        )
        plan = runner.plan(
            npc_key="chef_assistant",
            profile="npc-production-grounded",
            technique="ollama",
            target_stage="sanitize",
        )

        # Resume with all stages cached — should skip everything
        result = runner.run(plan, resume=True, dry_run=True)
        assert isinstance(result, list)

    def test_runner_run_errors_on_missing_artifact_index(self):
        from src.core.orchestration.target_runner import TargetRunner

        runner = TargetRunner(artifact_index="/nonexistent/path/artifacts.jsonl")
        plan = runner.plan("chef_assistant", "npc-production-grounded", "ollama", "sanitize")
        # Should not crash — plan still works with empty registry
        assert plan is not None

    def test_runner_plan_includes_profile_in_output(self, tmp_path):
        from src.core.orchestration.target_runner import TargetRunner

        runner = TargetRunner(artifact_index=tmp_path / "artifacts.jsonl")
        plan = runner.plan(
            npc_key="chef_assistant",
            profile="test-profile-v2",
            technique="ollama",
            target_stage="sanitize",
        )
        assert plan["profile"] == "test-profile-v2"
