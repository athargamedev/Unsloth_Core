from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops import ollama_lifecycle as ollama
from scripts.ops.model_presets import resolve_training_preset


def test_resolve_training_preset_prefers_explicit_exact_and_bucket_defaults():
    assert resolve_training_preset("unsloth/Llama-3.2-3B-Instruct-bnb-4bit") == "fast-3b"
    assert resolve_training_preset("unsloth/Llama-3.2-1B-Instruct-bnb-4bit") == "safe-any"
    assert resolve_training_preset("anything", preset="premium-3b") == "premium-3b"
    assert resolve_training_preset("unknown-model") == "fast-3b"


def test_unload_registered_ollama_models_stops_all_registered_models(monkeypatch):
    called: list[tuple[str, str]] = []

    def fake_stop(model_name: str, url: str) -> bool:
        called.append((model_name, url))
        return True

    monkeypatch.setattr(ollama, "stop_ollama_model", fake_stop)
    ollama._REGISTERED_UNLOADS.clear()
    ollama.register_ollama_unload("qwen3:latest", "http://localhost:11434")
    ollama.register_ollama_unload("llama3.1:latest", "http://localhost:11435")

    ollama.unload_registered_ollama_models()

    assert called == [
        ("qwen3:latest", "http://localhost:11434"),
        ("llama3.1:latest", "http://localhost:11435"),
    ]
