import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from scripts.evaluation.evaluate import generate_html_report, generate_report
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
    report_path = paths.eval_report_path("history_guide")
    feedback_path = paths.eval_feedback_path("history_guide")

    assert report_path == PROJECT_ROOT / "eval" / "reports" / "history_guide" / f"eval_{report_path.stem.split('_', 1)[1]}.md"
    assert feedback_path == PROJECT_ROOT / "eval" / "results" / "feedback" / "history_guide.json"


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

    weak = identify_weak_concepts(low_quality, win_rate_threshold=0.5, quality_threshold=20, violation_threshold=1)

    concepts = [item["concept"] for item in weak]
    assert "teaching/telescopes" in concepts
    assert "teaching/galaxies" not in concepts


def test_markdown_and_html_reports_create_parent_dirs(tmp_path):
    comparison = _comparison_result()
    md_path = tmp_path / "eval" / "reports" / "history_guide" / "eval_test.md"
    html_path = tmp_path / "eval" / "reports" / "history_guide" / "eval_test.html"

    markdown = generate_report(comparison, baseline_name="baseline", candidate_name="candidate", spec={"npc_name": "History Guide"}, output_path=md_path)
    generate_html_report(comparison, baseline_name="baseline", candidate_name="candidate", spec={"npc_name": "History Guide"}, output_path=html_path)

    assert md_path.exists()
    assert html_path.exists()
    assert "NPC Evaluation Report" in markdown
    assert "History Guide" in html_path.read_text()
