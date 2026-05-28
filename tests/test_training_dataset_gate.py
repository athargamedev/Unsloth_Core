import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dataset.dataset_contracts import summarize_jsonl_dataset
from scripts.training.train import dataset_quality_gate_errors, validation_dataset_path


def _write_clean_dataset(path: Path) -> dict:
    path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "Be concise."},
                    {"role": "user", "content": "Who are you?"},
                    {"role": "assistant", "content": "I am the guide."},
                ],
                "metadata": {"category": "identity", "difficulty": "beginner", "split": "train", "concept": "intro"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return summarize_jsonl_dataset(path)


def _write_quality_summary(path: Path, dataset_summary: dict, *, gate_mode: str = "release", failed: int = 0) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "total": 5,
                "failed": failed,
                "quality_gate_mode": gate_mode,
                "distribution_gaps": [],
                "dataset_unknown_rows": 0,
                "sanitizer_quality_issues": [],
                "dataset_summary": dataset_summary,
            }
        ),
        encoding="utf-8",
    )


def test_dataset_quality_gate_accepts_matching_passed_summary(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    _write_quality_summary(tmp_path / "quality_summary.json", dataset_summary)

    assert dataset_quality_gate_errors(clean_path) == []


def test_dataset_quality_gate_rejects_stale_summary_hash(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    _write_quality_summary(tmp_path / "quality_summary.json", dataset_summary)
    clean_path.write_text(clean_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    errors = dataset_quality_gate_errors(clean_path)

    assert any("does not match" in error for error in errors)


def test_dataset_quality_gate_accepts_fast_gate_with_metric_failures(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    _write_quality_summary(tmp_path / "quality_summary.json", dataset_summary, gate_mode="fast", failed=2)

    assert dataset_quality_gate_errors(clean_path) == []


def test_dataset_quality_gate_rejects_release_gate_metric_failures(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    _write_quality_summary(tmp_path / "quality_summary.json", dataset_summary, gate_mode="release", failed=1)

    errors = dataset_quality_gate_errors(clean_path)

    assert any("failing DeepEval cases" in error for error in errors)


def test_dataset_quality_gate_rejects_fast_gate_sanitizer_issues(tmp_path: Path):
    clean_path = tmp_path / "train_clean.jsonl"
    dataset_summary = _write_clean_dataset(clean_path)
    _write_quality_summary(tmp_path / "quality_summary.json", dataset_summary, gate_mode="fast", failed=0)
    summary_path = tmp_path / "quality_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["sanitizer_quality_issues"] = ["sanitizer flagged 1 row(s) for review"]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    errors = dataset_quality_gate_errors(clean_path)

    assert any("sanitizer quality issues" in error for error in errors)


def test_validation_dataset_path_prefers_clean_validation_split(tmp_path: Path):
    train_path = tmp_path / "train_clean.jsonl"
    raw_validation = tmp_path / "validation.jsonl"
    clean_validation = tmp_path / "validation_clean.jsonl"
    train_path.write_text("", encoding="utf-8")
    raw_validation.write_text("", encoding="utf-8")
    clean_validation.write_text("", encoding="utf-8")

    assert validation_dataset_path(train_path) == clean_validation
