import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from scripts.evaluation.evaluate import (
    build_eval_report_index,
    generate_html_report,
    generate_report,
)
from scripts.training.feedback_loop import identify_weak_concepts


def _comparison_result():
    return {
        "total": 1,
        "baseline_wins": 0,
        "candidate_wins": 1,
        "ties": 0,
        "comparisons": [
            {
                "question": "Explain telescopes.",
                "winner": "candidate",
                "baseline_metrics": {"quality": 18, "length": 40, "sentences": 2},
                "candidate_metrics": {"quality": 28, "length": 35, "sentences": 2},
                "metadata": {"category": "teaching", "concept": "telescopes"},
                "baseline": "baseline answer",
                "candidate": "candidate answer",
                "reasoning": "candidate is more specific",
            }
        ],
    }


def test_eval_paths_resolve_under_project_eval_root():
    report_path = paths.eval_report_path("history_guide", timestamp="20260521T123456_123456Z")
    html_path = paths.eval_report_path(
        "history_guide", fmt="html", timestamp="20260521T123456_123456Z"
    )
    comparison_path = paths.eval_comparison_path(
        "history_guide",
        "baseline_vs_candidate",
        timestamp="20260521T123456_123456Z",
    )
    feedback_path = paths.eval_feedback_path("history_guide")

    assert (
        report_path
        == paths.eval_root() / "reports" / "history_guide" / "eval_20260521T123456_123456Z.md"
    )
    assert (
        html_path
        == paths.eval_root() / "reports" / "history_guide" / "eval_20260521T123456_123456Z.html"
    )
    assert (
        comparison_path
        == paths.eval_root()
        / "comparisons"
        / "history_guide_vs_baseline_vs_candidate_20260521T123456_123456Z.md"
    )
    assert feedback_path == paths.eval_root() / "results" / "feedback" / "history_guide.json"


def test_feedback_loop_flags_low_quality_not_high_quality():
    low_quality = {
        "per_concept": {
            "teaching/telescopes": {
                "win_rate": 0.8,
                "avg_candidate_quality": 12,
                "constraint_violations": 0,
            },
            "teaching/galaxies": {
                "win_rate": 0.8,
                "avg_candidate_quality": 28,
                "constraint_violations": 0,
            },
        },
        "distribution_gaps": [],
    }

    weak = identify_weak_concepts(
        low_quality, win_rate_threshold=0.5, quality_threshold=20, violation_threshold=1
    )

    concepts = [item["concept"] for item in weak]
    assert "teaching/telescopes" in concepts
    assert "teaching/galaxies" not in concepts


def test_markdown_and_html_reports_create_parent_dirs(tmp_path):
    comparison = _comparison_result()
    md_path = tmp_path / "eval" / "reports" / "history_guide" / "eval_test.md"
    html_path = tmp_path / "eval" / "reports" / "history_guide" / "eval_test.html"

    markdown = generate_report(
        comparison,
        baseline_name="baseline",
        candidate_name="candidate",
        spec={"npc_name": "History Guide"},
        output_path=md_path,
    )
    generate_html_report(
        comparison,
        baseline_name="baseline",
        candidate_name="candidate",
        spec={"npc_name": "History Guide"},
        output_path=html_path,
    )

    assert md_path.exists()
    assert html_path.exists()
    assert "NPC Evaluation Report" in markdown
    assert "History Guide" in html_path.read_text()


def test_eval_report_index_categorizes_run_model_format_params_logic():
    comparison = {
        "total": 3,
        "baseline_wins": 1,
        "candidate_wins": 1,
        "ties": 1,
        "comparisons": [
            {
                "question": "Who are you?",
                "winner": "candidate",
                "baseline_metrics": {
                    "quality": 12,
                    "length": 44,
                    "sentences": 4,
                    "sentences_ok": False,
                    "name_ok": False,
                    "no_ai_disclaimer": True,
                    "has_think_tags": False,
                },
                "candidate_metrics": {
                    "quality": 28,
                    "length": 24,
                    "sentences": 2,
                    "sentences_ok": True,
                    "name_ok": True,
                    "no_ai_disclaimer": True,
                    "has_think_tags": False,
                },
                "metadata": {
                    "category": "identity",
                    "concept": "intro",
                    "difficulty": "beginner",
                    "format": "chatml",
                },
            },
            {
                "question": "Explain telescope evidence.",
                "winner": "baseline",
                "baseline_metrics": {
                    "quality": 30,
                    "length": 30,
                    "sentences": 2,
                    "sentences_ok": True,
                    "name_ok": True,
                    "no_ai_disclaimer": True,
                    "has_think_tags": False,
                },
                "candidate_metrics": {
                    "quality": 15,
                    "length": 90,
                    "sentences": 5,
                    "sentences_ok": False,
                    "name_ok": True,
                    "no_ai_disclaimer": True,
                    "has_think_tags": True,
                },
                "metadata": {
                    "category": "teaching",
                    "concept": "evidence",
                    "difficulty": "advanced",
                    "format": "chatml",
                },
            },
            {
                "question": "Tell me stock tips.",
                "winner": "tie",
                "baseline_metrics": {
                    "quality": 20,
                    "length": 30,
                    "sentences": 2,
                    "sentences_ok": True,
                    "name_ok": True,
                    "no_ai_disclaimer": True,
                    "has_think_tags": False,
                },
                "candidate_metrics": {
                    "quality": 20,
                    "length": 30,
                    "sentences": 2,
                    "sentences_ok": True,
                    "name_ok": True,
                    "no_ai_disclaimer": False,
                    "has_think_tags": False,
                },
                "metadata": {
                    "category": "refusal",
                    "concept": "boundary",
                    "difficulty": "beginner",
                    "format": "completion",
                },
            },
        ],
    }

    index = build_eval_report_index(
        comparison,
        baseline_name="base-q4.gguf",
        candidate_name="history_guide-lora-f16.gguf",
        spec={"npc_key": "history_guide", "npc_name": "History Guide"},
        run_metadata={
            "run_id": "eval-history_guide-qwen25-chatml-temp0.0-lora1.0-20260601",
            "base_model": "llama-3.2-3b-instruct-q4_k_m.gguf",
            "candidate_model": "history_guide-lora-f16.gguf",
            "candidate_format": "gguf_lora_adapter",
            "judge_model": "qwen2.5:7b",
            "parameters": {"temperature": 0.0, "lora_weight": 1.0, "max_tokens": 256},
            "logic_version": "heuristic+ollama-judge-v1",
            "confident": {
                "test_run_id": "tr_123",
                "url": "https://app.confident-ai.com/test-runs/tr_123",
            },
        },
    )

    assert index["run"]["npc_key"] == "history_guide"
    assert index["model"]["candidate_format"] == "gguf_lora_adapter"
    assert index["parameters"]["temperature"] == 0.0
    assert index["logic"]["version"] == "heuristic+ollama-judge-v1"
    assert index["confident"]["test_run_id"] == "tr_123"
    assert index["categories"]["identity"]["candidate_win_rate"] == 1.0
    assert index["categories"]["teaching"]["constraint_violations"] == 2
    assert index["formats"]["chatml"]["total"] == 2
    assert index["weak_slices"][0]["slice"] in {"teaching", "refusal"}
    assert "created_at" in index


def test_reports_render_categorized_comparison_sections():
    comparison = _comparison_result()
    index = build_eval_report_index(
        comparison,
        baseline_name="baseline",
        candidate_name="candidate",
        spec={"npc_key": "history_guide", "npc_name": "History Guide"},
        run_metadata={"parameters": {"temperature": 0.1}, "logic_version": "heuristic-v1"},
    )
    comparison["report_index"] = index

    markdown = generate_report(
        comparison,
        baseline_name="baseline",
        candidate_name="candidate",
        spec={"npc_name": "History Guide"},
    )
    html = generate_html_report(
        comparison,
        baseline_name="baseline",
        candidate_name="candidate",
        spec={"npc_name": "History Guide"},
    )

    assert "## Category Breakdown" in markdown
    assert "teaching" in markdown
    assert "## Run/Model/Parameter/Logic Index" in markdown
    assert "Category Breakdown" in html
    assert "Run/Model/Parameter/Logic Index" in html
