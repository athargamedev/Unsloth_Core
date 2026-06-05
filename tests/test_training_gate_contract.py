from __future__ import annotations

import json
from pathlib import Path

from scripts.dataset.dataset_contracts import summarize_jsonl_dataset
from scripts.ops.artifact_registry import ArtifactRegistry
from scripts.ops.pipeline_dag import stage_input_signature
from scripts.training.train import training_readiness_errors


def _write_clean_dataset(path: Path) -> dict:
    path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "Be grounded."},
                    {"role": "user", "content": "Who are you?"},
                    {"role": "assistant", "content": "I am the NPC."},
                ],
                "metadata": {"category": "identity", "difficulty": "beginner", "split": "train", "concept": "intro"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return summarize_jsonl_dataset(path)


def _write_quality_summary(path: Path, dataset_summary: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "total": 3,
                "failed": 0,
                "quality_gate_mode": "release",
                "distribution_gaps": [],
                "dataset_unknown_rows": 0,
                "sanitizer_quality_issues": [],
                "dataset_summary": dataset_summary,
            }
        ),
        encoding="utf-8",
    )


def test_training_readiness_rejects_passing_summary_without_fresh_registry_lineage(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    _write_quality_summary(tmp_path / "quality_summary.json", dataset_summary)
    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")

    errors = training_readiness_errors(clean_path, npc_key="chef_assistant", technique="ollama", registry=registry)

    assert any("Blocked: no fresh passing dataset-eval" in error for error in errors)
    assert any("Next: ./ucore dataset-eval" in error for error in errors)


def test_training_readiness_accepts_passing_summary_with_current_registry_lineage(tmp_path: Path):
    raw = tmp_path / "train.jsonl"
    raw.write_text("raw\n", encoding="utf-8")
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    summary_path = tmp_path / "quality_summary.json"
    _write_quality_summary(summary_path, dataset_summary)
    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")
    raw_record = registry.record_artifact("run-1", "chef_assistant", "generate", "dataset_raw", raw, technique="ollama")
    clean_record = registry.record_artifact(
        "run-2",
        "chef_assistant",
        "sanitize",
        "dataset_clean",
        clean_path,
        technique="ollama",
        metadata={"input_signature": stage_input_signature("sanitize", [raw_record])},
    )
    registry.record_artifact(
        "run-3",
        "chef_assistant",
        "dataset_eval",
        "quality_summary",
        summary_path,
        technique="ollama",
        metadata={"input_signature": stage_input_signature("dataset_eval", [clean_record])},
    )

    assert training_readiness_errors(clean_path, npc_key="chef_assistant", technique="ollama", registry=registry) == []


def test_training_readiness_allows_explicit_ungated_dev_bypass(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    _write_clean_dataset(clean_path)
    registry = ArtifactRegistry(tmp_path / "artifacts.jsonl")

    assert training_readiness_errors(
        clean_path,
        npc_key="chef_assistant",
        technique="template",
        registry=registry,
        allow_ungated_dataset=True,
    ) == []
