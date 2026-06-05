import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.dataset_eval import (
    DEFAULT_DATASET_EVAL_MODE,
    DEFAULT_FAST_CASES_PER_CATEGORY,
    DEFAULT_PRODUCTION_CASES_PER_CATEGORY,
    dataset_eval_exit_code,
    summarize_deepeval_result,
)


def test_dataset_eval_summary_extracts_metric_failures():
    result = {
        "identifier": "unit-run",
        "testCases": [
            {
                "name": "history_guide:teaching:1",
                "input": "User message",
                "actualOutput": "Generic answer",
                "success": False,
                "metadata": {
                    "npc_key": "history_guide",
                    "category": "teaching",
                    "concept": "cause and effect",
                    "source_path": "subjects/datasets/history_guide/template/train_clean.jsonl",
                    "line_number": 1,
                },
                "metricsData": [
                    {
                        "name": "Persona and Category Fit [GEval]",
                        "score": 0.8,
                        "threshold": 0.75,
                        "success": True,
                        "reason": "ok",
                        "evaluationModel": "qwen2.5:7b (Ollama)",
                    },
                    {
                        "name": "Training Usefulness and Specificity [GEval]",
                        "score": 0.4,
                        "threshold": 0.7,
                        "success": False,
                        "reason": "too generic",
                        "evaluationModel": "qwen2.5:7b (Ollama)",
                    },
                ],
            },
            {
                "name": "history_guide:refusal:2",
                "success": True,
                "metadata": {"category": "refusal"},
                "metricsData": [
                    {
                        "name": "Persona and Category Fit [GEval]",
                        "score": 0.9,
                        "threshold": 0.75,
                        "success": True,
                    }
                ],
            },
        ],
    }

    summary, failures = summarize_deepeval_result(
        result,
        npc_key="history_guide",
        technique="template",
        judge_model="qwen2.5:7b",
        command=["deepeval", "test", "run"],
    )

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["pass_rate"] == 0.5
    assert summary["categories"]["teaching"]["pass_rate"] == 0.0
    assert summary["categories"]["refusal"]["pass_rate"] == 1.0
    assert summary["metrics"]["Training Usefulness and Specificity [GEval]"]["average_score"] == 0.4
    assert len(failures) == 1
    assert failures[0]["metric"]["reason"] == "too generic"
    assert failures[0]["metadata"]["concept"] == "cause and effect"


def test_dataset_eval_summary_accepts_latest_test_run_payload():
    summary, failures = summarize_deepeval_result(
        {
            "testRunData": {
                "identifier": "unit-run",
                "testCases": [
                    {
                        "name": "case",
                        "success": True,
                        "metadata": {"category": "identity"},
                        "metricsData": [],
                    }
                ],
            }
        }.get("testRunData"),
        npc_key="history_guide",
        technique="template",
        judge_model="qwen2.5:7b",
        command=["deepeval", "test", "run"],
    )

    assert summary["total"] == 1
    assert summary["passed"] == 1
    assert failures == []


def test_dataset_eval_summary_marks_null_heavy_results_inconclusive():
    summary, failures = summarize_deepeval_result(
        {
            "identifier": "unit-run",
            "testCases": [
                {
                    "name": "case-1",
                    "success": False,
                    "metadata": {"category": "identity"},
                    "metricsData": [
                        {"name": "A", "score": None, "success": False},
                        {"name": "B", "score": None, "success": False},
                    ],
                }
            ],
        },
        npc_key="history_guide",
        technique="template",
        judge_model="qwen2.5:7b",
        command=["deepeval", "test", "run"],
    )

    assert summary["metric_count"] == 2
    assert summary["null_metric_count"] == 2
    assert summary["status"] == "inconclusive"
    assert len(failures) == 2


def test_dataset_eval_fast_mode_is_default_and_samples_one_case_per_category():
    assert DEFAULT_DATASET_EVAL_MODE == "fast"
    assert DEFAULT_FAST_CASES_PER_CATEGORY == 1


def test_dataset_eval_release_samples_five_cases_per_category():
    assert DEFAULT_PRODUCTION_CASES_PER_CATEGORY == 5


def test_fast_gate_metric_failures_are_diagnostic_not_blocking():
    summary = {
        "status": "ok",
        "failed": 3,
        "distribution_gaps": [],
        "dataset_unknown_rows": 0,
        "sanitizer_quality_issues": [],
    }

    assert dataset_eval_exit_code(summary, 1, "fast") == 0
    assert dataset_eval_exit_code(summary, 1, "release") == 1


def test_fast_gate_structural_failures_still_block():
    summary = {
        "status": "structural_failure",
        "failed": 0,
        "distribution_gaps": [{"category": "refusal", "shortfall": 1}],
        "dataset_unknown_rows": 0,
        "sanitizer_quality_issues": [],
    }

    assert dataset_eval_exit_code(summary, 0, "fast") == 2
