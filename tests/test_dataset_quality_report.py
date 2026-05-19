import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dataset_eval import build_combined_quality_report, summarize_jsonl_dataset


def test_combined_quality_report_merges_manifest_sanitize_and_deepeval(tmp_path: Path):
    spec = {
        "npc_key": "history_guide",
        "reference_doc": "subjects/reference_docs/history_guide_primer.md",
        "system_prompt": "IDENTITY\nVOICE\nKNOWLEDGE\nRULES",
        "__path__": "subjects/NPC_specs/history_guide.json",
    }

    clean_path = tmp_path / "train_clean.jsonl"
    clean_rows = [
        {
            "messages": [{"role": "user", "content": "What are you?"}, {"role": "assistant", "content": "I am a history guide."}],
            "metadata": {"category": "identity", "difficulty": "beginner", "split": "train", "concept": "identity"},
        },
        {
            "messages": [{"role": "user", "content": "Explain cause and effect."}, {"role": "assistant", "content": "Cause and effect links events."}],
            "metadata": {"category": "teaching", "difficulty": "intermediate", "split": "train", "concept": "cause and effect"},
        },
    ]
    clean_path.write_text("\n".join(json.dumps(row) for row in clean_rows) + "\n", encoding="utf-8")

    manifest_path = tmp_path / "train_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "sanitizer": {"version": "v2"},
                "input": {"file": "train.jsonl", "total_examples": 3},
                "statistics": {"total_output": 2},
                "discarded": {"total": 1},
            }
        ),
        encoding="utf-8",
    )

    dataset_summary = summarize_jsonl_dataset(clean_path)
    summary = {
        "created_at": "2026-05-19T00:00:00Z",
        "npc_key": "history_guide",
        "technique": "template",
        "judge_model": "qwen2.5:7b",
        "deepeval_identifier": "unit-run",
        "deepeval_result_identifier": "unit-run",
        "command": ["deepeval", "test", "run"],
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "metrics": {"Training Usefulness and Specificity [GEval]": {"count": 1, "average_score": 0.4, "pass_rate": 0.0}},
        "categories": {"identity": {"total": 1, "passed": 1, "pass_rate": 1.0}, "teaching": {"total": 1, "passed": 0, "pass_rate": 0.0}},
        "failures_path": str(tmp_path / "quality_failures.json"),
        "dataset_summary": dataset_summary,
        "expected_distribution": {"identity": 8, "teaching": 32, "dialogue": 16, "quest": 8, "refusal": 8},
        "distribution_gaps": [
            {"category": "teaching", "target": 32, "actual": 1, "shortfall": 31},
        ],
        "dataset_total_rows": 2,
        "dataset_unknown_rows": 0,
    }
    failures = [
        {
            "test_name": "history_guide:teaching:1",
            "input": "Explain cause and effect.",
            "actual_output": "Cause and effect links events.",
            "metadata": {"category": "teaching", "concept": "cause and effect"},
            "metric": {"name": "Training Usefulness and Specificity [GEval]", "score": 0.4, "threshold": 0.7, "success": False, "reason": "too generic"},
        }
    ]

    report = build_combined_quality_report(
        spec=spec,
        technique="template",
        clean_path=clean_path,
        manifest_path=manifest_path,
        summary=summary,
        failures=failures,
    )

    assert report["npc_key"] == "history_guide"
    assert report["manifest"]["sanitizer"]["version"] == "v2"
    assert report["dataset"]["summary"]["total"] == 2
    assert report["deepeval"]["summary"]["passed"] == 1
    assert report["feedback_signals"]
    assert any(signal["type"] == "distribution_gap" for signal in report["feedback_signals"])
    assert any(signal["type"] == "deepeval_metric_failure" for signal in report["feedback_signals"])
