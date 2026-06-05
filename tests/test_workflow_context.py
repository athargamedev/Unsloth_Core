from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import paths
from src.config.workflow_context import resolve_workflow_context


def _write_spec(root: Path, npc_key: str) -> Path:
    spec = {
        "npc_key": npc_key,
        "npc_name": npc_key.title().replace("_", ""),
        "subject": "Demo Subject",
        "system_prompt": "Keep answers short.",
        "dataset": {
            "examples_per_category": {
                "identity": 8,
                "teaching": 32,
                "dialogue": 16,
                "quest": 8,
                "refusal": 8,
            }
        },
    }
    spec_path = root / "subjects" / "NPC_specs" / f"{npc_key}.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return spec_path


def _write_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"messages": []}) + "\n", encoding="utf-8")


def test_resolve_workflow_context_prefers_existing_ollama_dataset(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    spec_path = _write_spec(tmp_path, "demo_npc")
    _write_jsonl(paths.dataset_train_path("demo_npc", "template"))
    _write_jsonl(paths.dataset_train_path("demo_npc", "ollama"))
    _write_jsonl(paths.dataset_train_path("demo_npc", "ollama").with_name("train_clean.jsonl"))
    _write_jsonl(paths.dataset_val_path("demo_npc", "ollama"))

    ctx = resolve_workflow_context(spec_path)

    assert ctx.npc_key == "demo_npc"
    assert ctx.technique == "ollama"
    assert ctx.dataset_train_path.name == "train_clean.jsonl"
    assert ctx.dataset_train_path.exists()
    assert ctx.dataset_val_path == paths.dataset_val_path("demo_npc", "ollama")


def test_resolve_workflow_context_prefers_requested_template_dataset(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    spec_path = _write_spec(tmp_path, "chef_demo")
    _write_jsonl(paths.dataset_train_path("chef_demo", "template"))
    _write_jsonl(paths.dataset_train_path("chef_demo", "template").with_name("train_clean.jsonl"))

    ctx = resolve_workflow_context(spec_path, technique="template")

    assert ctx.npc_key == "chef_demo"
    assert ctx.technique == "template"
    assert ctx.dataset_train_path.name == "train_clean.jsonl"
    assert ctx.dataset_val_path == paths.dataset_val_path("chef_demo", "template")


def test_resolve_workflow_context_uses_requested_missing_docs_dataset(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    spec_path = _write_spec(tmp_path, "history_demo")
    _write_jsonl(paths.dataset_train_path("history_demo", "ollama"))
    _write_jsonl(paths.dataset_train_path("history_demo", "ollama").with_name("train_clean.jsonl"))

    ctx = resolve_workflow_context(spec_path, technique="docs")

    assert ctx.npc_key == "history_demo"
    assert ctx.technique == "docs"
    assert ctx.dataset_train_path == paths.dataset_train_path("history_demo", "docs")
    assert ctx.dataset_val_path == paths.dataset_val_path("history_demo", "docs")
