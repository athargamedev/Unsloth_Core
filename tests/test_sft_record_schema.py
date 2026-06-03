from __future__ import annotations

import json
from pathlib import Path

import pytest


jsonschema = pytest.importorskip("jsonschema")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "data" / "npcs" / "schemas" / "sft_record.schema.json"
ACTIVE_DATASET_PATHS = [
    PROJECT_ROOT / "data" / "datasets" / "history_guide" / "ollama" / "train_clean.jsonl",
    PROJECT_ROOT / "data" / "datasets" / "chef_assistant" / "ollama" / "train_clean.jsonl",
]


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_sft_record_schema_carries_current_pipeline_metadata_contract():
    schema = _load_schema()
    metadata_props = schema["properties"]["metadata"]["properties"]

    assert schema["$id"].endswith("/data/npcs/schemas/sft_record.schema.json")
    assert "grounded" in metadata_props["technique"]["enum"]
    assert "turn_type" in metadata_props
    assert "quality_status" in metadata_props
    assert "metric_focus" in metadata_props
    assert "strategy_profile" in metadata_props
    assert "quality_gate_mode" in metadata_props
    assert "wandb_run_id" in metadata_props
    assert "confident_dataset_alias" in metadata_props
    assert "candidate_format" in metadata_props


def test_active_ollama_train_clean_rows_match_sft_record_schema():
    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    checked_rows = 0
    failures: list[str] = []

    for dataset_path in ACTIVE_DATASET_PATHS:
        assert dataset_path.exists(), f"Missing active dataset: {dataset_path}"
        with dataset_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                checked_rows += 1
                record = json.loads(line)
                for error in validator.iter_errors(record):
                    failures.append(f"{dataset_path}:{line_number}: {error.message}")

    assert checked_rows > 0
    assert failures == []
