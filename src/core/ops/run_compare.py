from __future__ import annotations

"""Compare canonical run bundles and emit a concise decision report."""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import json

from src.core.ops.run_index import load_bundle

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
COMPARISON_ROOT = PROJECT_ROOT / ".pipeline" / "comparisons"


@dataclass(frozen=True)
class RunComparison:
    baseline_run_id: str
    candidate_run_id: str
    baseline_path: str
    candidate_path: str
    winner: str
    metrics_delta: dict[str, Any]
    baseline: dict[str, Any]
    candidate: dict[str, Any]


def _score(bundle: dict[str, Any]) -> float:
    metrics = bundle.get("metrics") or {}
    score = 0.0
    for key in ("pass_rate", "pass_rate_pct"):
        if isinstance(metrics.get(key), (int, float)):
            score += float(metrics[key])
    for key in ("passed", "kept"):
        if isinstance(metrics.get(key), (int, float)):
            score += float(metrics[key]) * 0.1
    for key in ("discarded", "unknown_rows"):
        if isinstance(metrics.get(key), (int, float)):
            score -= float(metrics[key]) * 0.05
    return score


def compare_runs(baseline_path: Path, candidate_path: Path) -> RunComparison:
    baseline = load_bundle(baseline_path)
    candidate = load_bundle(candidate_path)
    baseline_score = _score(baseline)
    candidate_score = _score(candidate)
    winner = "candidate" if candidate_score > baseline_score else "baseline" if baseline_score > candidate_score else "tie"
    return RunComparison(
        baseline_run_id=str(baseline.get("run_id", baseline_path.parent.name)),
        candidate_run_id=str(candidate.get("run_id", candidate_path.parent.name)),
        baseline_path=str(baseline_path),
        candidate_path=str(candidate_path),
        winner=winner,
        metrics_delta={"baseline_score": baseline_score, "candidate_score": candidate_score, "delta": candidate_score - baseline_score},
        baseline=baseline,
        candidate=candidate,
    )


def write_comparison_report(comparison: RunComparison, output_path: Path | None = None) -> Path:
    path = output_path or (COMPARISON_ROOT / f"{comparison.baseline_run_id}_vs_{comparison.candidate_run_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(comparison), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path
