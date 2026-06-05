#!/usr/bin/env python3
"""Promotion decisions backed by canonical comparison records.

P6 invariant: promotion must be evidence-based. We inspect the append-only
ExperimentRegistry comparison records and never guess from "latest" artifact
pointers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.ops.experiment_registry import ExperimentRegistry


def promotion_decision(
    *,
    npc_key: str,
    candidate_run_id: str,
    registry_path: str | Path | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    registry = ExperimentRegistry(registry_path)
    source = registry.latest_comparison_for_candidate(
        npc_key=npc_key,
        candidate_run_id=candidate_run_id,
    )
    if not source:
        return {
            "can_promote": False,
            "reason": "no_comparison_record",
            "npc_key": npc_key,
            "candidate_run_id": candidate_run_id,
            "dry_run": dry_run,
        }

    comparison = source.get("comparison") or {}
    winner = comparison.get("winner")
    can_promote = winner == "candidate"
    return {
        "can_promote": can_promote,
        "reason": "candidate_won_comparison" if can_promote else f"winner_is_{winner or 'unknown'}",
        "npc_key": npc_key,
        "candidate_run_id": candidate_run_id,
        "baseline_run_id": comparison.get("baseline_run_id"),
        "source_comparison_run_id": source.get("run_id"),
        "metrics_delta": comparison.get("metrics_delta") or {},
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Promote a model using canonical comparison evidence"
    )
    parser.add_argument("--npc-key", required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--registry-path", default=None)
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only; currently the safe default"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    decision = promotion_decision(
        npc_key=args.npc_key,
        candidate_run_id=args.candidate_run_id,
        registry_path=args.registry_path,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(decision, indent=2, default=str))
    else:
        status = "PROMOTABLE" if decision["can_promote"] else "BLOCKED"
        print(f"{status}: {decision['reason']}")
    return 0 if decision["can_promote"] or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
