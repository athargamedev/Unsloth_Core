import json
from pathlib import Path

from scripts.dataset_contracts import (
    MIN_DATASET_EXAMPLES_PER_CATEGORY,
    calculate_distribution_gaps,
    expected_examples_per_category,
    summarize_jsonl_dataset,
)


def test_expected_examples_per_category_defaults_to_contract_minimums():
    assert expected_examples_per_category(None) == MIN_DATASET_EXAMPLES_PER_CATEGORY


def test_expected_examples_per_category_uses_spec_targets():
    spec = {
        "dataset": {
            "examples_per_category": {
                "identity": 10,
                "teaching": 40,
                "dialogue": 20,
                "quest": 12,
                "refusal": 8,
            }
        }
    }

    assert expected_examples_per_category(spec)["teaching"] == 40
    assert expected_examples_per_category(spec)["identity"] == 10


def test_calculate_distribution_gaps_reports_shortfalls():
    gaps = calculate_distribution_gaps(
        {"identity": 8, "teaching": 32, "dialogue": 16, "quest": 8, "refusal": 8},
        {"identity": 8, "teaching": 30, "dialogue": 16, "quest": 5, "refusal": 8},
    )

    assert {gap["category"] for gap in gaps} == {"teaching", "quest"}
    assert next(gap for gap in gaps if gap["category"] == "quest")["shortfall"] == 3


def test_summarize_jsonl_dataset_counts_rows(tmp_path: Path):
    dataset_path = tmp_path / "train_clean.jsonl"
    rows = [
        {"messages": [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}], "metadata": {"category": "identity", "difficulty": "beginner", "split": "train", "concept": "intro"}},
        {"messages": [{"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"}], "metadata": {"category": "teaching", "difficulty": "intermediate", "split": "validation", "concept": "concept"}},
    ]
    dataset_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    summary = summarize_jsonl_dataset(dataset_path)

    assert summary["total"] == 2
    assert summary["by_category"] == {"identity": 1, "teaching": 1}
    assert summary["by_difficulty"] == {"beginner": 1, "intermediate": 1}
    assert summary["by_split"] == {"train": 1, "validation": 1}
