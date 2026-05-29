from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.contract


def test_workflow_path_helpers_resolve_under_expected_roots(monkeypatch, tmp_path):
    from _config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    npc = "demo_npc"

    assert paths.npc_config_dir(npc) == tmp_path / "configs" / "npcs" / npc
    assert paths.npc_workflow_config_path(npc) == tmp_path / "configs" / "npcs" / npc / "workflow.yaml"
    assert paths.npc_workflow_manifest_path(npc) == tmp_path / "outputs" / npc / "workflow_manifest.json"
    assert paths.npc_log_root(npc) == tmp_path / "logs" / npc
    assert paths.npc_log_dir(npc, "training") == tmp_path / "logs" / npc / "training"
    assert paths.npc_pipeline_root(npc) == tmp_path / ".pipeline" / "npcs" / npc
    assert paths.npc_pipeline_index_path(npc) == tmp_path / ".pipeline" / "npcs" / npc / "index.json"

    assert paths.dataset_manifest_path(npc, "docs") == tmp_path / "subjects" / "datasets" / npc / "docs" / "manifests" / "dataset_manifest.json"
    assert paths.generation_config_path(npc, "docs") == tmp_path / "subjects" / "datasets" / npc / "docs" / "generation_config.json"
    assert paths.dataset_log_dir(npc, "docs") == tmp_path / "subjects" / "datasets" / npc / "docs" / "logs"

    assert paths.training_config_path(npc) == tmp_path / "configs" / "npcs" / npc / "training.yaml"
    assert paths.evaluation_config_path(npc) == tmp_path / "configs" / "npcs" / npc / "evaluation.yaml"
    assert paths.sweep_dir(npc) == tmp_path / "configs" / "npcs" / npc / "sweeps"
    assert paths.export_adapter_dir(npc) == tmp_path / "exports" / npc / "adapters"
    assert paths.export_unity_alias_path(npc) == tmp_path / "exports" / npc / "unity" / f"{npc}-lora-f16.gguf"


def test_artifact_id_is_stable_safe_and_encodes_core_context():
    from _config.artifact_ids import build_artifact_id, params_hash, slugify_artifact_part

    params = {"lora_r": 16, "epochs": 5, "lr": 0.0002}
    assert params_hash(params) == params_hash({"epochs": 5, "lr": 0.0002, "lora_r": 16})
    assert slugify_artifact_part("unsloth/Llama-3.2-3B-Instruct-bnb-4bit") == "llama-3-2-3b-instruct-bnb-4bit"

    artifact_id = build_artifact_id(
        npc_key="history_guide",
        dataset_technique="notebooklm",
        base_model="unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
        generation_preset="nblm-v1",
        training_preset="fast-3b",
        eval_model="qwen2.5:7b",
        params=params,
        timestamp="20260529T121958Z",
    )

    assert artifact_id.startswith("history_guide__ds-notebooklm__base-llama-3-2-3b")
    assert "__gen-nblm-v1__" in artifact_id
    assert "__train-fast-3b__" in artifact_id
    assert "__eval-qwen2-5-7b__" in artifact_id
    assert "__p-" in artifact_id
    assert artifact_id.endswith("__20260529T121958Z")
    assert len(artifact_id) <= 180


def test_audit_tests_outputs_matrix(tmp_path):
    output_json = tmp_path / "matrix.json"
    output_md = tmp_path / "matrix.md"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/ops/audit_tests.py",
            "--write",
            str(output_json),
            "--markdown",
            str(output_md),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "test_files" in result.stdout
    payload = json.loads(output_json.read_text())
    assert payload["summary"]["test_files"] >= 20
    assert any(item["file"] == "tests/test_workflow_context.py" for item in payload["tests"])
    assert "# Test Process Matrix" in output_md.read_text()


def test_suite_audit_has_no_unknown_owners(tmp_path):
    output_json = tmp_path / "matrix.json"
    subprocess.run(
        [sys.executable, "scripts/ops/audit_tests.py", "--write", str(output_json)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(output_json.read_text())
    unknown = [item["file"] for item in payload["tests"] if item["owner"] == "unknown"]
    assert not unknown


def test_ucore_exposes_current_core_commands():
    result = subprocess.run([sys.executable, "./ucore", "--help"], cwd=PROJECT_ROOT, text=True, capture_output=True, check=True)
    help_text = result.stdout
    for command in [
        "generate",
        "sanitize",
        "dataset-eval",
        "train",
        "export",
        "evaluate",
        "feedback",
        "pipeline",
        "validate-spec",
    ]:
        assert command in help_text


def test_ucore_rejects_resume_from_flag_for_train():
    result = subprocess.run(
        [sys.executable, "./ucore", "train", "subjects/NPC_specs/history_guide.json", "--resume-from", "x"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "resume-from" in result.stderr
