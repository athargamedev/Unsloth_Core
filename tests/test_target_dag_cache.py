from __future__ import annotations

from pathlib import Path


def test_target_plan_skips_cached_stage_when_output_signature_matches_inputs(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry
    from scripts.ops.pipeline_dag import PipelineDAG, stage_input_signature

    raw = tmp_path / "train.jsonl"
    raw.write_text('{"messages": []}\n', encoding="utf-8")
    clean = tmp_path / "train_clean.jsonl"
    clean.write_text('{"messages": []}\n', encoding="utf-8")

    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    raw_record = registry.record_artifact("run-1", "chef_assistant", "generate", "dataset_raw", raw, technique="ollama")
    signature = stage_input_signature("sanitize", [raw_record])
    registry.record_artifact(
        "run-1",
        "chef_assistant",
        "sanitize",
        "dataset_clean",
        clean,
        technique="ollama",
        metadata={"input_signature": signature},
    )

    plan = PipelineDAG(registry=registry).plan_target("sanitize", npc_key="chef_assistant", technique="ollama")

    assert plan["ready"] is True
    assert plan["steps"][-1]["stage"] == "sanitize"
    assert plan["steps"][-1]["status"] == "cached"
    assert plan["steps"][-1]["action"] == "skip"


def test_target_plan_marks_stage_stale_when_latest_input_hash_changes(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry
    from scripts.ops.pipeline_dag import PipelineDAG, stage_input_signature

    raw = tmp_path / "train.jsonl"
    raw.write_text("old\n", encoding="utf-8")
    clean = tmp_path / "train_clean.jsonl"
    clean.write_text("clean from old\n", encoding="utf-8")

    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    old_raw_record = registry.record_artifact("run-1", "chef_assistant", "generate", "dataset_raw", raw, technique="ollama")
    registry.record_artifact(
        "run-1",
        "chef_assistant",
        "sanitize",
        "dataset_clean",
        clean,
        technique="ollama",
        metadata={"input_signature": stage_input_signature("sanitize", [old_raw_record])},
    )

    raw.write_text("new\n", encoding="utf-8")
    registry.record_artifact("run-2", "chef_assistant", "generate", "dataset_raw", raw, technique="ollama")

    plan = PipelineDAG(registry=registry).plan_target("sanitize", npc_key="chef_assistant", technique="ollama")

    sanitize_step = plan["steps"][-1]
    assert plan["ready"] is False
    assert sanitize_step["status"] == "stale"
    assert sanitize_step["action"] == "run"
    assert sanitize_step["reason"] == "input_signature_changed"


def test_target_plan_reports_missing_first_stage_output(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry
    from scripts.ops.pipeline_dag import PipelineDAG

    plan = PipelineDAG(registry=ArtifactRegistry(tmp_path / "artifacts.jsonl")).plan_target(
        "sanitize", npc_key="chef_assistant", technique="ollama"
    )

    assert plan["ready"] is False
    assert plan["steps"][0]["stage"] == "generate"
    assert plan["steps"][0]["status"] == "missing"
    assert plan["steps"][0]["action"] == "run"
