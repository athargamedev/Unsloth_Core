from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from _config.workflow_context import resolve_workflow_context


def test_resolve_workflow_context_prefers_existing_ollama_dataset_for_history_guide():
    ctx = resolve_workflow_context("subjects/NPC_specs/history_guide.json")
    assert ctx.npc_key == "history_guide"
    assert ctx.technique == "ollama"
    assert ctx.dataset_train_path.name == "train_clean.jsonl"
    assert ctx.dataset_train_path.exists()
    assert ctx.dataset_val_path.name == "validation.jsonl"
    assert ctx.dataset_val_path == paths.dataset_val_path("history_guide", "ollama")


def test_resolve_workflow_context_prefers_existing_ollama_dataset_for_chef_assistant():
    ctx = resolve_workflow_context("subjects/NPC_specs/chef_assistant.json")
    assert ctx.npc_key == "chef_assistant"
    assert ctx.technique == "ollama"
    assert ctx.dataset_train_path.name == "train_clean.jsonl"
    assert ctx.dataset_train_path.exists()
    assert ctx.dataset_val_path == paths.dataset_val_path("chef_assistant", "ollama")
