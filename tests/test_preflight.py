import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops import preflight


def test_run_preflight_auto_downgrades_fast3b_and_stops_ollama(tmp_path, monkeypatch):
    spec_path = tmp_path / "chef_assistant.json"
    spec_path.write_text(
        json.dumps(
            {
                "npc_key": "chef_assistant",
                "model": "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
                "dataset": {"examples_per_category": {"identity": 1}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(preflight, "query_gpu_memory", lambda: (0.9, 4.5))
    monkeypatch.setattr(preflight, "check_gcc", lambda: (True, "/usr/bin/gcc", None))
    monkeypatch.setattr(preflight, "list_running_ollama_models", lambda url: ["qwen2.5:7b"])
    monkeypatch.setattr(preflight, "stop_running_models", lambda url: ["qwen2.5:7b"])

    report = preflight.run_preflight(
        phase="train",
        preset="fast-3b",
        spec_path=spec_path,
        technique="template",
        ollama_url="http://localhost:11434",
        auto_unload_ollama=True,
        require_gcc=True,
    )

    assert report.preset_requested == "fast-3b"
    assert report.preset_effective == "safe-any"
    assert report.stopped_ollama_models == ["qwen2.5:7b"]
    assert report.gcc_ok is True
    assert report.status == "degraded"
    assert any("Auto-fallback" in warning for warning in report.warnings)


def test_run_preflight_blocks_when_gcc_missing(monkeypatch):
    monkeypatch.setattr(preflight, "query_gpu_memory", lambda: (2.0, 5.67))
    monkeypatch.setattr(preflight, "check_gcc", lambda: (False, None, "gcc not found in PATH"))
    monkeypatch.setattr(preflight, "list_running_ollama_models", lambda url: [])

    report = preflight.run_preflight(
        phase="train",
        preset="safe-any",
        spec_path=None,
        technique="template",
        ollama_url="http://localhost:11434",
        auto_unload_ollama=True,
        require_gcc=True,
    )

    assert report.status == "blocked"
    assert "gcc not found in PATH" in report.errors[0]
