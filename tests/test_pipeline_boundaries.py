import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def minimal_spec():
    return {
        "npc_key": "demo_npc",
        "npc_name": "DemoNpc",
        "subject": "Demo Studies",
        "system_prompt": "You are DemoNpc.",
        "dataset": {"examples_per_category": {"identity": 1}},
    }


def test_dataset_technique_priority_order(monkeypatch, tmp_path):
    from _config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    # Create datasets for two techniques; ollama has higher priority than template
    for technique in ("ollama", "template"):
        write_jsonl(paths.dataset_train_path("demo_npc", technique), [{"messages": []}])
        write_jsonl(paths.dataset_val_path("demo_npc", technique), [{"messages": []}])

    technique, train_path, val_path = paths.autodetect_dataset("demo_npc")

    assert "onyx" not in paths.DATASET_TECHNIQUES
    assert "ollama" in paths.DATASET_TECHNIQUES
    assert "template" in paths.DATASET_TECHNIQUES
    assert technique == "ollama"
    assert train_path == paths.dataset_train_path("demo_npc", "ollama")
    assert val_path == paths.dataset_val_path("demo_npc", "ollama")



def test_ollama_generator_output_shape_is_chatml(tmp_path):
    from scripts.generate_dataset import generate_dataset

    class FakeGenerator:
        model = "fake"

        def generate(self, *args, **kwargs):
            return json.dumps({"user": "What is demo?", "assistant": "Demo is a test."})

    result_path = tmp_path / "train.jsonl"
    result = generate_dataset(minimal_spec(), result_path, include_validation=False, generator=FakeGenerator())
    first = json.loads(result_path.read_text().splitlines()[0])

    assert result["train"] == 1
    assert [m["role"] for m in first["messages"]] == ["system", "user", "assistant"]
    assert first["metadata"]["source"].startswith("ollama:")



def test_smoke_custom_prompts_and_tracking_timestamp(monkeypatch, tmp_path, capsys):
    from scripts import smoke_test

    model_path = tmp_path / "model.gguf"
    model_path.write_text("stub")
    monkeypatch.setattr(sys, "argv", ["smoke_test.py", str(model_path), "--prompt", "Custom one"])
    monkeypatch.setattr(smoke_test, "run_llama_cli", lambda *args, **kwargs: "Healthy response")

    smoke_test.main()

    out = capsys.readouterr().out
    assert "Custom one" in out
    assert "1/1 prompts passed" in out


def test_tracking_local_fallback_shape(tmp_path):
    from scripts.track_eval_results import track_result

    results_file = tmp_path / "eval_results.jsonl"
    saved_to_supabase = track_result(
        "demo_npc",
        "exports/demo/model.gguf",
        win_rate=0.5,
        notes="summary",
        results_file=results_file,
        metadata={"test_type": "unit"},
    )

    record = json.loads(results_file.read_text().strip())
    assert saved_to_supabase is False
    assert record["npc_key"] == "demo_npc"
    assert record["metadata"]["test_type"] == "unit"


def test_export_latest_resolution_keeps_npc_key(monkeypatch, tmp_path):
    from _config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    run_dir = paths.run_dir("demo_npc", "20260512_fast_001")
    run_dir.mkdir(parents=True)
    (run_dir / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "unsloth/Test"}))
    latest = paths.output_dir("demo_npc") / "latest"
    latest.symlink_to("runs/20260512_fast_001", target_is_directory=True)

    npc_key, adapter_dir = paths.resolve_adapter_dir("demo_npc")

    assert npc_key == "demo_npc"
    assert adapter_dir == run_dir.resolve()
