#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.ops.run_compare import compare_runs, write_comparison_report
from src.core.ops.run_index import latest_bundle_for_run, refresh_run_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two canonical run bundles")
    parser.add_argument("baseline_run_id")
    parser.add_argument("candidate_run_id")
    parser.add_argument("--output", default=None)
    parser.add_argument("--refresh-index", action="store_true")
    args = parser.parse_args()
    if args.refresh_index:
        refresh_run_index()
    baseline = latest_bundle_for_run(args.baseline_run_id)
    candidate = latest_bundle_for_run(args.candidate_run_id)
    if not baseline or not candidate:
        raise SystemExit("Missing canonical bundle for one or both run ids")
    report = compare_runs(baseline, candidate)
    path = write_comparison_report(report, Path(args.output) if args.output else None)
    print(path)


if __name__ == "__main__":
    main()
