import json
import os
import sys
from pathlib import Path

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
    from src.config import paths

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
    from src.core.dataset._generate_shared import generate_dataset

    class FakeGenerator:
        model = "fake"

        def generate(self, *args, **kwargs):
            return json.dumps({"user": "What is demo?", "assistant": "Demo is a test."})

    result_path = tmp_path / "train.jsonl"
    result = generate_dataset(
        minimal_spec(), result_path, include_validation=False, generator=FakeGenerator()
    )
    first = json.loads(result_path.read_text().splitlines()[0])

    assert result["train"] == 1
    assert [m["role"] for m in first["messages"]] == ["system", "user", "assistant"]
    assert first["metadata"]["source"].startswith("ollama:")


def test_concept_extractor_uses_explicit_concepts_and_metadata():
    from src.core.dataset._generate_shared import ConceptExtractor

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


def test_concept_extractor_ignores_meta_reference_headings():
    from src.core.dataset._generate_shared import ConceptExtractor

    spec = {
        "npc_key": "chef_assistant",
        "npc_name": "ChefAssistant",
        "subject": "Cooking fundamentals: knife skills, heat, flavor, food safety, and kitchen workflow",
        "reference_doc": "data/npcs/reference_docs/chef_assistant_primer.md",
        "teaching": {"expertise": ["knife skills", "flavor balance"]},
    }

    concepts = [c.name for c in ConceptExtractor(spec).extract()]

    assert "scope and use" not in concepts
    assert "misconceptions and refusals" not in concepts


def test_smoke_custom_prompts_and_tracking_timestamp(monkeypatch, tmp_path, capsys):
    from src.core import smoke_test

    model_path = tmp_path / "model.gguf"
    model_path.write_text("stub")
    monkeypatch.setattr(sys, "argv", ["smoke_test.py", str(model_path), "--prompt", "Custom one"])
    monkeypatch.setattr(smoke_test, "run_llama_cli", lambda *args, **kwargs: "Healthy response")

    smoke_test.main()

    out = capsys.readouterr().out
    assert "Custom one" in out
    assert "1/1 prompts passed" in out


def test_tracking_local_fallback_shape(tmp_path):
    from src.core.track_eval_results import track_result

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
    from src.config import paths

    from src.config import paths as src_paths
    from src.core import sanitize_dataset

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(src_paths, "PROJECT_ROOT", tmp_path)
    train_path = paths.dataset_train_path("demo_npc", "ollama")
    val_path = paths.dataset_val_path("demo_npc", "ollama")
    train_path.parent.mkdir(parents=True)
    write_jsonl(train_path, [{"messages": []}, {"messages": []}])
    write_jsonl(val_path, [{"messages": []}, {"messages": []}, {"messages": []}])

    relative_train_path = Path("subjects/datasets/demo_npc/ollama/train.jsonl")

    assert sanitize_dataset.infer_technique_from_path(relative_train_path) == "ollama"
    assert sanitize_dataset.count_sibling_validation_examples(relative_train_path) == 3


def test_refusal_structural_check_requires_boundary_or_redirect():
    from src.core.sanitize_dataset import refusal_response_has_boundary

    assert refusal_response_has_boundary(
        "I can't confirm that claim, but I can help with evidence from astronomy."
    )
    assert not refusal_response_has_boundary(
        "The possibility is exciting, so let's explore moons and asteroids that might support life."
    )


def test_refusal_boundary_markers_catch_safety_refusals():
    """All 6 previously-dropped 'unsafe shortcuts' refusal patterns must be recognized."""
    from src.core.sanitize_dataset import refusal_response_has_boundary

    patterns = [
        "Nope. Food safety isn't negotiable. Use a thermometer to check internal temperature.",
        "No, never skip food safety steps. Let the chicken rest at the proper temperature.",
        "That's unsafe. Bacteria grow quickly at room temperature. Always refrigerate promptly.",
        "No shortcuts when it comes to food safety. Use a meat thermometer every time.",
        "Nope. Safety first - always check temps with a reliable thermometer.",
        "Nope. Letting meat sit out risks bacteria growth. Refrigerate within two hours.",
    ]
    for i, text in enumerate(patterns):
        assert refusal_response_has_boundary(text), (
            f"Safety refusal pattern {i + 1} should be recognized: {text[:60]}..."
        )

    # Mix of markers across patterns must all pass
    assert refusal_response_has_boundary("Nope. I won't endorse unsafe kitchen practices.")
    assert refusal_response_has_boundary("Absolutely not. Never skip the resting period.")
    assert refusal_response_has_boundary("That's unsafe and it's not safe to recommend.")
    assert refusal_response_has_boundary("Don't skip proper cooling procedures.")
    assert refusal_response_has_boundary("The risk of foodborne illness is too high.")
    assert refusal_response_has_boundary("Safety is not negotiable when handling poultry.")


def test_refusal_boundary_markers_dont_falsely_match_teaching():
    """Teaching responses about food safety or bacteria must NOT be flagged as having boundaries."""
    from src.core.sanitize_dataset import refusal_response_has_boundary

    non_refusals = [
        "Bacteria are single-celled organisms that can be found in various environments.",
        "Food safety involves proper handling, cooking, and storage of food to prevent illness.",
        "Always check the internal temperature with a meat thermometer to ensure doneness.",
        "Cross-contamination can occur when raw meat touches other foods in the kitchen.",
        "The first safety rule in the kitchen is to wash your hands thoroughly.",
    ]
    for i, text in enumerate(non_refusals):
        assert not refusal_response_has_boundary(text), (
            f"Non-refusal {i + 1} should not match: {text[:60]}..."
        )


def test_refusal_response_includes_boundary_and_redirect():
    from src.core.dataset.generation_profiles import generate_refusal_response

    spec = {
        "npc_name": "HistoryGuide",
        "subject": "world history",
    }

    response = generate_refusal_response(spec, boundary="misinformation or conspiracy")

    lower = response.lower()
    assert any(
        marker in lower
        for marker in [
            "i can't",
            "i cannot",
            "outside my scope",
            "evidence-based",
            "not supported by evidence",
        ]
    )
    assert any(
        marker in lower
        for marker in ["instead", "let's focus", "i can help with", "what i can do", "a safer way"]
    )
    assert any(marker in lower for marker in ["world history", "chronology", "sources", "evidence"])


def test_ollama_category_prompts_remain_short_and_specific():
    from src.core.generate_dataset_ollama import build_category_generation_prompt

    identity = build_category_generation_prompt("identity", "ancient civilizations", "HistoryGuide")
    teaching = build_category_generation_prompt("teaching", "ancient civilizations", "HistoryGuide")
    dialogue = build_category_generation_prompt("dialogue", "ancient civilizations", "HistoryGuide")
    refusal = build_category_generation_prompt("refusal", "ancient civilizations", "HistoryGuide")

    assert "name one historical method or focus" in identity or "chronology or sources" in identity
    assert "generic storyteller language" in identity
    assert "direct answer" in teaching
    assert "one concrete fact or example" in teaching
    assert "Aim for 35-55 words" in teaching
    assert "Aim for 35-55 words" in dialogue
    assert "one grounded detail or example" in dialogue
    assert "why it matters in play" in dialogue
    assert "Aim for 35-55 words" in dialogue
    assert "do not add an unrelated fact" in refusal.lower()
    assert "drift to another topic" in refusal.lower()
    assert "Instead, I can help with" in refusal
    assert (
        "one concrete in-scope topic related to history, such as chronology or sources" in refusal
    )


def test_ollama_multi_turn_selection_is_deterministic():
    from src.core.generate_dataset_ollama import should_generate_multi_turn

    first = [should_generate_multi_turn("teaching", i, 0.25) for i in range(12)]
    second = [should_generate_multi_turn("teaching", i, 0.25) for i in range(12)]

    assert first == second
    assert any(first)
    assert not all(first)


def test_template_generation_avoids_duplicate_refusal_rows(tmp_path):
    from src.core.dataset._generate_shared import generate_dataset
    from src.core.dataset.dataset_contracts import (
        calculate_distribution_gaps,
        expected_examples_per_category,
        summarize_jsonl_dataset,
    )

    spec = {
        "npc_key": "history_guide",
        "npc_name": "HistoryGuide",
        "subject": "World history: ancient civilizations and historical thinking",
        "system_prompt": "## IDENTITY\nName: HistoryGuide\n## VOICE\nConcise\n## KNOWLEDGE\nWorld history\n## RULES\nUse evidence.",
        "identity": {
            "personality": "Careful",
            "background": "History tutor",
            "mannerisms": "Uses sources",
        },
        "dialogue": {
            "max_sentences": 3,
            "max_characters": 220,
            "example_topics": ["What caused the fall of Rome?"],
        },
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
        "dataset": {
            "examples_per_category": {
                "identity": 2,
                "teaching": 4,
                "dialogue": 4,
                "quest": 3,
                "refusal": 8,
            }
        },
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
    assert (
        calculate_distribution_gaps(expected_examples_per_category(spec), summary["by_category"])
        == []
    )


def test_export_resolution_keeps_npc_key(monkeypatch, tmp_path):
    from src.config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    run_dir = paths.run_dir("demo_npc", "20260512_fast_001")
    run_dir.mkdir(parents=True)
    (run_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "unsloth/Test"})
    )
    latest = paths.output_dir("demo_npc") / "latest"
    latest.symlink_to("runs/20260512_fast_001", target_is_directory=True)

    npc_key, adapter_dir = paths.resolve_adapter_dir("demo_npc")

    assert npc_key == "demo_npc"
    assert adapter_dir == run_dir.resolve()


def test_export_resolution_falls_back_to_newest_run_without_symlinks(monkeypatch, tmp_path):
    from src.config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    older = paths.run_dir("demo_npc", "20260512_fast_001")
    newer = paths.run_dir("demo_npc", "20260512_fast_002")
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "unsloth/Test"})
    )
    (newer / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "unsloth/Test"})
    )
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_000_100, 1_700_000_100))

    npc_key, adapter_dir = paths.resolve_adapter_dir(paths.output_dir("demo_npc"))

    assert npc_key == "demo_npc"
    assert adapter_dir == newer.resolve()


def test_validate_spec_generation_ready_requires_reference_contract(monkeypatch, tmp_path):
    from src.core import validate_subject_spec as validator

    spec = minimal_spec()
    spec["identity"] = {
        "personality": "patient",
        "background": "demo expert",
        "mannerisms": "clear",
    }
    spec["teaching"] = {
        "expertise": ["demo concepts"],
        "approach": "explain simply",
        "difficulty_levels": ["beginner"],
    }
    spec["dialogue"] = {"max_sentences": 3, "example_topics": ["What is demo?"]}
    spec["quest"] = {"scenarios": [{"name": "demo", "description": "demo task"}]}
    spec["refusal"] = {
        "boundaries": ["unsafe demo claims"],
        "redirect_policy": "redirect to evidence",
    }
    spec["research_queries"] = [{"query": "demo facts", "mode": "fast"}]
    spec["dataset"] = {
        "examples_per_category": {
            "identity": 1,
            "teaching": 1,
            "dialogue": 1,
            "quest": 1,
            "refusal": 1,
        }
    }
    spec["reference_doc"] = "data/npcs/reference_docs/demo_primer.md"

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
    from src.core.validate_subject_spec import find_subject_specs, validate_spec

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


def test_trim_to_max_sentences():
    from src.core.dataset.sanitize_dataset import trim_to_max_sentences

    assert trim_to_max_sentences("", 2) == ""
    assert trim_to_max_sentences("Hello.", 0) == ""

    # Simple trim
    text1 = "Sentence one. Sentence two. Sentence three."
    assert trim_to_max_sentences(text1, 2) == "Sentence one. Sentence two."
    assert trim_to_max_sentences(text1, 1) == "Sentence one."
    assert trim_to_max_sentences(text1, 5) == "Sentence one. Sentence two. Sentence three."

    # Abbreviation handling
    text2 = "Dr. Smith went home. He was very happy. This is sentence three."
    assert trim_to_max_sentences(text2, 1) == "Dr. Smith went home."
    assert trim_to_max_sentences(text2, 2) == "Dr. Smith went home. He was very happy."

    # Ellipsis handling
    text3 = "Wait for it... It was great! Yes."
    assert trim_to_max_sentences(text3, 1) == "Wait for it... It was great!"
    assert trim_to_max_sentences(text3, 2) == "Wait for it... It was great! Yes."

    # Appending punctuation if missing
    assert trim_to_max_sentences("Hello", 1) == "Hello."


def test_repair_and_filter_artifacts():
    from src.core.dataset.sanitize_dataset import repair_and_filter_artifacts

    # Clean text unchanged
    assert repair_and_filter_artifacts("Hello there. How are you?") == "Hello there. How are you?"

    # AI artifact filtered
    text = "Hello. As an AI, I don't have feelings. But I can help you."
    # The middle sentence has "As an AI". It should be filtered out.
    assert repair_and_filter_artifacts(text) == "Hello. But I can help you."


def test_artifact_check_repair_mode():
    from src.core.dataset.sanitize_dataset import sanitize_example

    example = {
        "messages": [
            {"role": "system", "content": "You are a guide."},
            {"role": "user", "content": "Tell me a story."},
            {
                "role": "assistant",
                "content": "Sure. As an AI language model, I love stories. Once upon a time, a hero saved the day.",
            },
        ],
        "metadata": {"npc_key": "history_guide", "category": "dialogue"},
    }

    # Under strict check, it gets discarded/refused
    clean, score, warnings, reason = sanitize_example(
        example, "data/npcs/history_guide/train.jsonl", artifact_check="strict"
    )
    assert clean is None
    assert "Contains AI artifact" in reason

    # Under repair check, it is cleaned and kept
    clean, score, warnings, reason = sanitize_example(
        example, "data/npcs/history_guide/train.jsonl", artifact_check="repair"
    )
    assert clean is not None
    assert reason is None
    # Verify the middle sentence with artifact was filtered
    assistant_content = clean["messages"][-1]["content"]
    assert "language model" not in assistant_content
    assert "Sure." in assistant_content
    assert "Once upon a time" in assistant_content
    assert any("Repaired AI artifact" in w for w in warnings)


def test_score_rule_compliance_sliding_scale_and_command_verbs():
    from src.core.dataset.sanitize_dataset import score_rule_compliance

    # 1. Sliding scale check for sentence count
    # Let's mock an example where response is:
    # 1 sentence over (max 2): "One. Two. Three." -> sentence count = 3 -> 1 sentence over -> -1 penalty -> score 9
    example1 = {
        "messages": [
            {"role": "user", "content": "Is this a test?"},
            {"role": "assistant", "content": "One. Two. Three."},
        ]
    }
    score1 = score_rule_compliance(example1, max_sentences=2)
    # Total score starts at 10.
    # sentence count = 3. max = 2. 1 sentence over -> score starts at 10, -1 = 9.
    assert score1 == 9

    # 2 sentences over (max 1): "One. Two. Three." -> sentence count = 3 -> 2 sentences over -> -2 penalty -> score 8
    score2 = score_rule_compliance(example1, max_sentences=1)
    assert score2 == 8

    # >2 sentences over (max 1): "One. Two. Three. Four." -> sentence count = 4 -> 3 sentences over -> -3 penalty -> score 7
    example2 = {
        "messages": [
            {"role": "user", "content": "Is this a test?"},
            {"role": "assistant", "content": "One. Two. Three. Four."},
        ]
    }
    score3 = score_rule_compliance(example2, max_sentences=1)
    assert score3 == 7

    # 2. Command verb question mark penalty bypass
    # Without command verb, user msg with no ? gets -1 penalty -> score 9
    example3 = {
        "messages": [
            {"role": "user", "content": "You should check this"},
            {"role": "assistant", "content": "Sure, I will do that."},
        ]
    }
    assert score_rule_compliance(example3) == 9

    # With command verb (e.g. "Introduce yourself"), user msg with no ? skips penalty -> score 10
    example4 = {
        "messages": [
            {"role": "user", "content": "Introduce yourself to me"},
            {"role": "assistant", "content": "Sure, I will do that."},
        ]
    }
    assert score_rule_compliance(example4) == 10

    # With lowercase command verb ("tell"), skips penalty -> score 10
    example5 = {
        "messages": [
            {"role": "user", "content": "tell me a story"},
            {"role": "assistant", "content": "Sure, I will do that."},
        ]
    }
    assert score_rule_compliance(example5) == 10


def test_local_gap_detector(tmp_path, monkeypatch):
    from src.config import paths

    class LocalGapDetector:
        def __init__(self, npc_key: str, technique: str = "template"):
            self.npc_key = npc_key
            self.technique = technique
            self.spec_path = paths.spec_path(npc_key)
            self.primer_path = tmp_path / "data" / "npcs" / "reference_docs" / f"{npc_key}_primer.md"
            self.train_clean_path = paths.dataset_dir(npc_key) / technique / "train_clean.jsonl"
            self.spec_concepts = []
            self.primer_text = ""
            self._load()

        def _load(self):
            self.spec_concepts = json.loads(self.spec_path.read_text()).get("concepts", [])
            self.primer_text = self.primer_path.read_text()

        def count_primer_occurrences(self, concept_name: str, aliases: list[str]) -> int:
            text_lower = self.primer_text.lower()
            count = text_lower.count(concept_name.lower().strip())
            for alias in aliases:
                count += text_lower.count(alias.lower().strip())
            return count

        def count_training_examples(self, concept_name: str) -> int:
            count = 0
            target = concept_name.lower().strip()
            with self.train_clean_path.open(encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    ex_concept = data.get("metadata", {}).get("concept")
                    if ex_concept and ex_concept.lower().strip() == target:
                        count += 1
            return count

        def detect_gaps(self, weak_concepts: list[dict]) -> list[dict]:
            gap_results = []
            for wc in weak_concepts:
                concept_key = wc["concept"]
                reasons = wc.get("reasons", [])
                category, concept_name = concept_key.split("/", 1) if "/" in concept_key else (None, concept_key)
                spec_c = next(
                    (
                        c
                        for c in self.spec_concepts
                        if c.get("name", "").lower().strip() == concept_name.lower().strip()
                        and (category is None or c.get("category", "").lower().strip() == category.lower().strip())
                    ),
                    None,
                )
                aliases = spec_c.get("aliases", []) if spec_c else []
                canonical_name = spec_c.get("name", concept_name) if spec_c else concept_name
                primer_occurrences = self.count_primer_occurrences(canonical_name, aliases)
                training_examples_count = self.count_training_examples(canonical_name)
                if primer_occurrences == 0:
                    gap_type = "knowledge_gap"
                    rec = "Source document lacks coverage. Add descriptive sections to primer."
                elif training_examples_count < 8:
                    gap_type = "training_density_gap"
                    rec = "Low example density. Trigger synthetic generation for concept with focus."
                else:
                    gap_type = "model_capacity_gap"
                    rec = "The model failed to acquire the concept; upgrade training preset, increase epochs, or check format."
                gap_results.append(
                    {
                        "concept": concept_key,
                        "gap_type": gap_type,
                        "primer_occurrences": primer_occurrences,
                        "training_examples_count": training_examples_count,
                        "action_recommendation": rec,
                        "reasons": reasons,
                    }
                )
            return gap_results

    # Set up mock spec, primer, and train_clean files
    npc_key = "test_npc"
    technique = "template"

    spec_dir = tmp_path / "data" / "npcs" / "specs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / f"{npc_key}.json"

    spec_data = {
        "concepts": [
            {"name": "Swordplay", "category": "teaching", "aliases": ["fencing", "blade"]},
            {"name": "Archery", "category": "teaching", "aliases": ["bow", "arrows"]},
            {"name": "Magic", "category": "teaching", "aliases": ["spells", "alchemy"]},
        ]
    }
    spec_file.write_text(json.dumps(spec_data))

    primer_dir = tmp_path / "data" / "npcs" / "reference_docs"
    primer_dir.mkdir(parents=True, exist_ok=True)
    primer_file = primer_dir / f"{npc_key}_primer.md"

    # "swordplay" is in primer, "magic" is in primer, "archery" is NOT in primer.
    primer_text = "The guide to fencing and blade skills. Magic and spells are also vital."
    primer_file.write_text(primer_text)

    dataset_dir = tmp_path / "data" / "datasets" / npc_key / technique
    dataset_dir.mkdir(parents=True, exist_ok=True)
    train_clean_file = dataset_dir / "train_clean.jsonl"

    # Training records:
    # "magic" has 9 examples (>= 8)
    # "swordplay" has 3 examples (< 8)
    # "archery" has 0 examples (< 8)
    records = []
    for _ in range(9):
        records.append({"messages": [], "metadata": {"concept": "Magic"}})
    for _ in range(3):
        records.append({"messages": [], "metadata": {"concept": "swordplay"}})

    write_jsonl(train_clean_file, records)

    # Patch the PROJECT_ROOT to our tmp_path
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    from src.config import paths as src_paths

    monkeypatch.setattr(src_paths, "PROJECT_ROOT", tmp_path)

    # Initialize detector
    detector = LocalGapDetector(npc_key, technique=technique)

    # Verify spec concepts and primer loaded
    assert len(detector.spec_concepts) == 3
    assert "fencing" in detector.primer_text

    # Run detect_gaps
    weak_concepts = [
        {"concept": "teaching/Archery", "reasons": ["low quality"]},
        {"concept": "teaching/Swordplay", "reasons": ["low win rate"]},
        {"concept": "teaching/Magic", "reasons": ["high violations"]},
    ]

    gaps = detector.detect_gaps(weak_concepts)

    # Classify results:
    # 1. Archery -> 0 occurrences in primer -> knowledge_gap
    archery_gap = next(g for g in gaps if g["concept"] == "teaching/Archery")
    assert archery_gap["gap_type"] == "knowledge_gap"
    assert "Source document lacks coverage" in archery_gap["action_recommendation"]
    assert archery_gap["primer_occurrences"] == 0
    assert archery_gap["training_examples_count"] == 0

    # 2. Swordplay -> 2 occurrences (fencing, blade), 3 examples (< 8) -> training_density_gap
    swordplay_gap = next(g for g in gaps if g["concept"] == "teaching/Swordplay")
    assert swordplay_gap["gap_type"] == "training_density_gap"
    assert "Low example density" in swordplay_gap["action_recommendation"]
    assert swordplay_gap["primer_occurrences"] == 2
    assert swordplay_gap["training_examples_count"] == 3

    # 3. Magic -> 2 occurrences (magic, spells), 9 examples (>= 8) -> model_capacity_gap
    magic_gap = next(g for g in gaps if g["concept"] == "teaching/Magic")
    assert magic_gap["gap_type"] == "model_capacity_gap"
    assert "failed to acquire the concept" in magic_gap["action_recommendation"]
    assert magic_gap["primer_occurrences"] == 2
    assert magic_gap["training_examples_count"] == 9
