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


def test_refusal_boundary_markers_catch_safety_refusals():
    """All 6 previously-dropped 'unsafe shortcuts' refusal patterns must be recognized."""
    from scripts.sanitize_dataset import refusal_response_has_boundary

    patterns = [
        "Nope. Food safety isn't negotiable. Use a thermometer to check internal temperature.",
        "No, never skip food safety steps. Let the chicken rest at the proper temperature.",
        "That's unsafe. Bacteria grow quickly at room temperature. Always refrigerate promptly.",
        "No shortcuts when it comes to food safety. Use a meat thermometer every time.",
        "Nope. Safety first - always check temps with a reliable thermometer.",
        "Nope. Letting meat sit out risks bacteria growth. Refrigerate within two hours.",
    ]
    for i, text in enumerate(patterns):
        assert refusal_response_has_boundary(text), \
            f"Safety refusal pattern {i+1} should be recognized: {text[:60]}..."

    # Mix of markers across patterns must all pass
    assert refusal_response_has_boundary("Nope. I won't endorse unsafe kitchen practices.")
    assert refusal_response_has_boundary("Absolutely not. Never skip the resting period.")
    assert refusal_response_has_boundary("That's unsafe and it's not safe to recommend.")
    assert refusal_response_has_boundary("Don't skip proper cooling procedures.")
    assert refusal_response_has_boundary("The risk of foodborne illness is too high.")
    assert refusal_response_has_boundary("Safety is not negotiable when handling poultry.")


def test_refusal_boundary_markers_dont_falsely_match_teaching():
    """Teaching responses about food safety or bacteria must NOT be flagged as having boundaries."""
    from scripts.sanitize_dataset import refusal_response_has_boundary

    non_refusals = [
        "Bacteria are single-celled organisms that can be found in various environments.",
        "Food safety involves proper handling, cooking, and storage of food to prevent illness.",
        "Always check the internal temperature with a meat thermometer to ensure doneness.",
        "Cross-contamination can occur when raw meat touches other foods in the kitchen.",
        "The first safety rule in the kitchen is to wash your hands thoroughly.",
    ]
    for i, text in enumerate(non_refusals):
        assert not refusal_response_has_boundary(text), \
            f"Non-refusal {i+1} should not match: {text[:60]}..."


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
    assert any(marker in lower for marker in ["world history", "chronology", "sources", "evidence"])


def test_ollama_category_prompts_remain_short_and_specific():
    from scripts.generate_dataset_ollama import build_category_generation_prompt

    identity = build_category_generation_prompt("identity", "ancient civilizations", "HistoryGuide")
    teaching = build_category_generation_prompt("teaching", "ancient civilizations", "HistoryGuide")
    dialogue = build_category_generation_prompt("dialogue", "ancient civilizations", "HistoryGuide")
    refusal = build_category_generation_prompt("refusal", "ancient civilizations", "HistoryGuide")

    assert "name one historical method or focus" in identity or "chronology or sources" in identity
    assert "generic storyteller language" in identity
    assert "1-2 short sentences" in teaching
    assert "one concrete fact or example" in teaching
    assert "Aim for 12-20 words" in teaching
    assert "under 200 characters" in dialogue
    assert "one specific detail or example" in dialogue
    assert "aim for 12-20 words" in dialogue
    assert "do not add an unrelated history fact" in refusal.lower()
    assert "drift to another topic" in refusal.lower()
    assert "Instead, I can help with" in refusal
    assert "one concrete in-scope topic like chronology or sources" in refusal


def test_ollama_multi_turn_selection_is_deterministic():
    from scripts.generate_dataset_ollama import should_generate_multi_turn

    first = [should_generate_multi_turn("teaching", i, 0.25) for i in range(12)]
    second = [should_generate_multi_turn("teaching", i, 0.25) for i in range(12)]

    assert first == second
    assert any(first)
    assert not all(first)


def test_template_generation_avoids_duplicate_refusal_rows(tmp_path):
    from scripts.dataset.generate_dataset import generate_dataset
    from scripts.dataset.dataset_contracts import calculate_distribution_gaps, expected_examples_per_category, summarize_jsonl_dataset

    spec = {
        "npc_key": "history_guide",
        "npc_name": "HistoryGuide",
        "subject": "World history: ancient civilizations and historical thinking",
        "system_prompt": "## IDENTITY\nName: HistoryGuide\n## VOICE\nConcise\n## KNOWLEDGE\nWorld history\n## RULES\nUse evidence.",
        "identity": {"personality": "Careful", "background": "History tutor", "mannerisms": "Uses sources"},
        "dialogue": {"max_sentences": 3, "max_characters": 220, "example_topics": ["What caused the fall of Rome?"]},
        "teaching": {"difficulty_levels": ["beginner", "intermediate"]},
        "quest": {"scenarios": [{"name": "timeline_analysis", "description": "Practice sequence"}]},
        "refusal": {
            "boundaries": [
                "Will not present speculation as fact",
                "Will not promote conspiracy theories or historical misinformation",
            ]
        },
        "concepts": [
            {"name": "ancient civilizations", "category": "teaching", "difficulty": "beginner"},
            {"name": "historical thinking", "category": "dialogue", "difficulty": "intermediate"},
            {"name": "timeline analysis", "category": "quest", "difficulty": "intermediate"},
        ],
        "dataset": {"examples_per_category": {"identity": 2, "teaching": 4, "dialogue": 4, "quest": 3, "refusal": 8}},
    }

    output_path = tmp_path / "train.jsonl"
    result = generate_dataset(
        spec,
        output_path,
        include_validation=False,
        seed=42,
        technique="template",
        workflow_hooks=tmp_path / "workflow_hooks.jsonl",
    )
    summary = summarize_jsonl_dataset(output_path)
    hashes = set()
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        hashes.add(row["metadata"]["content_hash"])

    assert result["total"] == 21
    assert summary["by_category"]["refusal"] == 8
    assert len(hashes) == summary["total"]
    assert calculate_distribution_gaps(expected_examples_per_category(spec), summary["by_category"]) == []


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
