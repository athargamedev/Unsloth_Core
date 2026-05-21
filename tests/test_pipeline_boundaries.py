import json
import os
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



def test_concept_extractor_uses_explicit_concepts_and_metadata():
    from scripts.generate_dataset import ConceptExtractor

    spec = minimal_spec()
    spec["teaching"] = {
        "expertise": ["demo concepts"],
        "approach": "explain simply",
        "difficulty_levels": {"demo concepts": "intermediate"},
    }
    spec["concepts"] = [
        {
            "name": "special topic",
            "category": "teaching",
            "difficulty": "advanced",
            "aliases": ["specialized topic"],
        }
    ]

    concepts = ConceptExtractor(spec).extract()
    explicit = [c for c in concepts if c.name == "special topic"]

    assert explicit, "Explicit concept should be present in extracted concepts"
    assert explicit[0].category == "teaching"
    assert explicit[0].difficulty == "advanced"
    assert "specialized topic" in explicit[0].aliases



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


def test_sanitizer_infers_relative_technique_and_counts_sibling_validation(monkeypatch, tmp_path):
    from _config import paths
    from scripts import sanitize_dataset

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    train_path = paths.dataset_train_path("demo_npc", "ollama")
    val_path = paths.dataset_val_path("demo_npc", "ollama")
    train_path.parent.mkdir(parents=True)
    write_jsonl(train_path, [{"messages": []}, {"messages": []}])
    write_jsonl(val_path, [{"messages": []}, {"messages": []}, {"messages": []}])

    relative_train_path = Path("subjects/datasets/demo_npc/ollama/train.jsonl")

    assert sanitize_dataset.infer_technique_from_path(relative_train_path) == "ollama"
    assert sanitize_dataset.count_sibling_validation_examples(relative_train_path) == 3


def test_refusal_structural_check_requires_boundary_or_redirect():
    from scripts.sanitize_dataset import refusal_response_has_boundary

    assert refusal_response_has_boundary("I can't confirm that claim, but I can help with evidence from astronomy.")
    assert not refusal_response_has_boundary("The possibility is exciting, so let's explore moons and asteroids that might support life.")


def test_refusal_response_includes_boundary_and_redirect():
    from importlib import import_module

    gd = import_module("scripts.generate_dataset")

    spec = {
        "npc_name": "HistoryGuide",
        "subject": "world history",
    }

    response = gd.generate_refusal_response(spec, boundary="misinformation or conspiracy")

    lower = response.lower()
    assert any(marker in lower for marker in ["i can't", "i cannot", "outside my scope", "evidence-based", "not supported by evidence"])
    assert any(marker in lower for marker in ["instead", "let's focus", "i can help with", "what i can do", "a safer way"])
    assert "world history" in lower


def test_ollama_cleaner_replaces_generic_filler():
    from scripts.generate_dataset_ollama import clean_generic_filler

    raw = "Great question. Once you understand this, everything falls into place naturally."
    cleaned = clean_generic_filler(raw, concept="telescopes")

    assert "everything falls into place" not in cleaned.lower()
    assert "telescopes" in cleaned.lower()


def test_ollama_multi_turn_selection_is_deterministic():
    from scripts.generate_dataset_ollama import should_generate_multi_turn

    first = [should_generate_multi_turn("teaching", i, 0.25) for i in range(12)]
    second = [should_generate_multi_turn("teaching", i, 0.25) for i in range(12)]

    assert first == second
    assert any(first)
    assert not all(first)


def test_export_resolution_keeps_npc_key(monkeypatch, tmp_path):
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


def test_export_resolution_falls_back_to_newest_run_without_symlinks(monkeypatch, tmp_path):
    from _config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    older = paths.run_dir("demo_npc", "20260512_fast_001")
    newer = paths.run_dir("demo_npc", "20260512_fast_002")
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "unsloth/Test"}))
    (newer / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "unsloth/Test"}))
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    npc_key, adapter_dir = paths.resolve_adapter_dir(paths.output_dir("demo_npc"))

    assert npc_key == "demo_npc"
    assert adapter_dir == newer.resolve()



def test_validate_spec_generation_ready_requires_reference_contract(monkeypatch, tmp_path):
    from scripts import validate_subject_spec as validator

    spec = minimal_spec()
    spec["identity"] = {"personality": "patient", "background": "demo expert", "mannerisms": "clear"}
    spec["teaching"] = {"expertise": ["demo concepts"], "approach": "explain simply", "difficulty_levels": ["beginner"]}
    spec["dialogue"] = {"max_sentences": 3, "example_topics": ["What is demo?"]}
    spec["quest"] = {"scenarios": [{"name": "demo", "description": "demo task"}]}
    spec["refusal"] = {"boundaries": ["unsafe demo claims"], "redirect_policy": "redirect to evidence"}
    spec["research_queries"] = [{"query": "demo facts", "mode": "fast"}]
    spec["dataset"] = {"examples_per_category": {"identity": 1, "teaching": 1, "dialogue": 1, "quest": 1, "refusal": 1}}
    spec["reference_doc"] = "subjects/reference_docs/demo_primer.md"

    root = tmp_path
    monkeypatch.setattr(validator, "PROJECT_ROOT", root)
    spec_path = root / "subjects" / "demo_npc.json"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(json.dumps(spec))
    ref_path = root / spec["reference_doc"]
    ref_path.parent.mkdir(parents=True)
    ref_path.write_text("# Demo\n\n## Facts\n- one\n")

    result = validator.validate_spec(
        spec_path,
        require_reference_docs=True,
        require_reference_contract=True,
        require_all_categories=True,
        require_dataset_minimums=True,
    )

    assert result.errors
    assert any("Reference doc must have at least" in error for error in result.errors)
    assert any("dataset.examples_per_category.teaching" in error for error in result.errors)


def test_all_current_specs_are_generation_ready():
    from scripts.validate_subject_spec import find_subject_specs, validate_spec

    results = [
        validate_spec(
            path,
            require_reference_docs=True,
            require_reference_contract=True,
            require_all_categories=True,
            require_dataset_minimums=True,
        )
        for path in find_subject_specs()
    ]

    failures = {result.path: result.errors for result in results if result.errors}
    assert failures == {}
