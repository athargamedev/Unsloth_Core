#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.ops.experiment_registry import ExperimentRegistry, ExperimentRun
from src.core.ops.run_compare import RunComparison, compare_runs, write_comparison_report
from src.core.ops.run_index import latest_bundle_for_run, refresh_run_index


def compare_and_record(
    baseline_run_id: str,
    candidate_run_id: str,
    *,
    runs_root: Path | None = None,
    comparisons_root: Path | None = None,
    output_path: Path | None = None,
    registry_path: Path | str | None = None,
) -> tuple[Path, RunComparison]:
    """Compare canonical bundles and append a canonical ExperimentRun record."""
    baseline = latest_bundle_for_run(baseline_run_id, root=runs_root)
    candidate = latest_bundle_for_run(candidate_run_id, root=runs_root)
    if not baseline or not candidate:
        raise SystemExit("Missing canonical bundle for one or both run ids")

    comparison = compare_runs(baseline, candidate)
    if output_path is None and comparisons_root is not None:
        output_path = (
            comparisons_root / f"{comparison.baseline_run_id}_vs_{comparison.candidate_run_id}.json"
        )
    report_path = write_comparison_report(comparison, output_path)

    comparison_record = asdict(comparison)
    candidate_bundle = comparison_record.get("candidate") or {}
    npc_key = str(candidate_bundle.get("npc_key") or "unknown")
    technique = str(candidate_bundle.get("technique") or "unknown")
    ExperimentRegistry(registry_path).record_run(
        ExperimentRun(
            run_id=f"compare_{comparison.baseline_run_id}_vs_{comparison.candidate_run_id}",
            npc_key=npc_key,
            stage="compare",
            technique=technique,
            status="complete",
            metrics=comparison_record.get("metrics_delta") or {},
            artifacts={"comparison_report": str(report_path)},
            comparison=comparison_record,
        )
    )
    return report_path, comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two canonical run bundles")
    parser.add_argument("baseline_run_id")
    parser.add_argument("candidate_run_id")
    parser.add_argument("--output", default=None)
    parser.add_argument("--refresh-index", action="store_true")
    parser.add_argument("--registry-path", default=None, help="ExperimentRegistry JSONL path")
    parser.add_argument("--json", action="store_true", help="Output structured JSON")
    args = parser.parse_args()
    if args.refresh_index:
        refresh_run_index()
    path, comparison = compare_and_record(
        args.baseline_run_id,
        args.candidate_run_id,
        output_path=Path(args.output) if args.output else None,
        registry_path=args.registry_path,
    )
    if args.json:
        print(
            json.dumps(
                {"report_path": str(path), "comparison": asdict(comparison)}, indent=2, default=str
            )
        )
    else:
        print(path)


if __name__ == "__main__":
    main()
