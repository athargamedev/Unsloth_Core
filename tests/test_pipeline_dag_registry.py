from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_pipeline_dag_blocks_stage_when_required_artifacts_missing(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry
    from scripts.ops.pipeline_dag import PipelineDAG

    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    dag = PipelineDAG(registry=registry)

    result = dag.validate_stage("train", npc_key="history_guide", technique="notebooklm")

    assert result.ok is False
    assert result.stage == "train"
    assert "dataset_eval" in result.missing_stages
    assert "dataset_clean" in result.missing_artifacts
    assert result.next_required_stage == "generate"


def test_pipeline_dag_allows_stage_after_prerequisite_artifacts_exist(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry
    from scripts.ops.pipeline_dag import PipelineDAG

    clean = tmp_path / "train_clean.jsonl"
    clean.write_text('{"messages": []}\n', encoding="utf-8")
    quality = tmp_path / "quality_summary.json"
    quality.write_text('{"passed": true}\n', encoding="utf-8")

    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    registry.record_artifact(
        "run-1", "history_guide", "sanitize", "dataset_clean", clean, technique="notebooklm"
    )
    registry.record_artifact(
        "run-1", "history_guide", "dataset_eval", "quality_summary", quality, technique="notebooklm"
    )

    result = PipelineDAG(registry=registry).validate_stage(
        "train", npc_key="history_guide", technique="notebooklm"
    )

    assert result.ok is True
    assert result.missing_stages == []
    assert result.missing_artifacts == []


def test_artifact_registry_records_hash_and_queries_latest_by_type(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry

    artifact = tmp_path / "eval.index.json"
    artifact.write_text(json.dumps({"schema_version": "eval_report_index.v1"}), encoding="utf-8")
    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")

    record = registry.record_artifact(
        run_id="eval-run-1",
        npc_key="history_guide",
        stage="evaluate",
        artifact_type="eval_index",
        path=artifact,
        technique="notebooklm",
        metadata={"judge_model": "qwen2.5:7b"},
    )

    latest = registry.latest_artifact("history_guide", "eval_index", technique="notebooklm")
    assert latest is not None
    assert latest["run_id"] == "eval-run-1"
    assert latest["sha256"] == record["sha256"]
    assert latest["metadata"]["judge_model"] == "qwen2.5:7b"
    assert latest["exists"] is True


def test_record_stage_artifacts_maps_canonical_stage_outputs(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry, record_stage_artifacts

    raw = tmp_path / "train.jsonl"
    raw.write_text('{"messages": []}\n', encoding="utf-8")
    clean = tmp_path / "train_clean.jsonl"
    clean.write_text('{"messages": []}\n', encoding="utf-8")
    quality = tmp_path / "quality_summary.json"
    quality.write_text('{"passed": 1, "total": 1}\n', encoding="utf-8")
    run_dir = tmp_path / "outputs" / "history_guide" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    gguf = tmp_path / "history_guide-lora-f16.gguf"
    gguf.write_bytes(b"gguf")
    eval_index = tmp_path / "eval.index.json"
    eval_index.write_text("{}", encoding="utf-8")

    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    record_stage_artifacts(
        registry, "run-1", "history_guide", "generate", {"train": raw}, technique="notebooklm"
    )
    record_stage_artifacts(
        registry, "run-1", "history_guide", "sanitize", {"output": clean}, technique="notebooklm"
    )
    record_stage_artifacts(
        registry,
        "run-1",
        "history_guide",
        "dataset_eval",
        {"quality_summary": quality},
        technique="notebooklm",
    )
    record_stage_artifacts(
        registry, "run-1", "history_guide", "train", {"run_dir": run_dir}, technique="notebooklm"
    )
    record_stage_artifacts(
        registry, "run-1", "history_guide", "export", {"gguf": gguf}, technique="notebooklm"
    )
    record_stage_artifacts(
        registry,
        "run-1",
        "history_guide",
        "evaluate",
        {"eval_index": eval_index},
        technique="notebooklm",
    )

    assert registry.latest_artifact("history_guide", "dataset_raw", technique="notebooklm")[
        "path"
    ] == str(raw)
    assert registry.latest_artifact("history_guide", "dataset_clean", technique="notebooklm")[
        "path"
    ] == str(clean)
    assert registry.latest_artifact("history_guide", "quality_summary", technique="notebooklm")[
        "path"
    ] == str(quality)
    assert registry.latest_artifact("history_guide", "adapter_checkpoint", technique="notebooklm")[
        "path"
    ] == str(run_dir)
    assert registry.latest_artifact("history_guide", "gguf_adapter", technique="notebooklm")[
        "path"
    ] == str(gguf)
    assert registry.latest_artifact("history_guide", "eval_index", technique="notebooklm")[
        "path"
    ] == str(eval_index)


def test_record_stage_artifacts_can_attach_input_lineage_metadata(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry, record_stage_artifacts
    from scripts.ops.pipeline_dag import stage_input_signature

    raw = tmp_path / "train.jsonl"
    raw.write_text("raw rows\n", encoding="utf-8")
    clean = tmp_path / "train_clean.jsonl"
    clean.write_text("clean rows\n", encoding="utf-8")
    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    raw_record = registry.record_artifact(
        "run-1", "history_guide", "generate", "dataset_raw", raw, technique="ollama"
    )

    record_stage_artifacts(
        registry,
        "run-2",
        "history_guide",
        "sanitize",
        {"output": clean},
        technique="ollama",
        input_records=[raw_record],
        producer_command="./ucore sanitize train.jsonl --technique ollama",
        profile="npc-production-grounded",
    )

    latest = registry.latest_artifact("history_guide", "dataset_clean", technique="ollama")
    metadata = latest["metadata"]
    assert metadata["input_hashes"] == {"dataset_raw": raw_record["sha256"]}
    assert metadata["input_signature"] == stage_input_signature("sanitize", [raw_record])
    assert metadata["producer_command"] == "./ucore sanitize train.jsonl --technique ollama"
    assert metadata["profile"] == "npc-production-grounded"


def test_pipeline_dag_writes_plan_with_ordered_blockers(tmp_path):
    from scripts.ops.artifact_registry import ArtifactRegistry
    from scripts.ops.pipeline_dag import PipelineDAG

    plan = PipelineDAG(registry=ArtifactRegistry(tmp_path / "artifacts.jsonl")).plan_to_stage(
        "evaluate", npc_key="chef_assistant", technique="notebooklm"
    )

    assert [step["stage"] for step in plan["steps"]] == [
        "generate",
        "sanitize",
        "dataset_eval",
        "train",
        "export",
        "evaluate",
    ]
    assert plan["target_stage"] == "evaluate"
    assert plan["ready"] is False
    assert plan["steps"][0]["ready"] is True
    assert plan["steps"][-1]["ready"] is False


def test_ucore_audit_pipeline_plan_writes_json(tmp_path):
    output = tmp_path / "plan.json"
    result = __import__("subprocess").run(
        [
            sys.executable,
            "./ucore",
            "audit",
            "pipeline-plan",
            "--npc-key",
            "history_guide",
            "--technique",
            "notebooklm",
            "--target-stage",
            "train",
            "--artifact-index",
            str(tmp_path / "artifacts.jsonl"),
            "--write",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(output.read_text())
    assert payload["npc_key"] == "history_guide"
    assert payload["target_stage"] == "train"
    assert "pipeline plan written" in result.stdout.lower()
