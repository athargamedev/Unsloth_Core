#!/usr/bin/env python3
"""Push local NPC evaluation datasets to Confident AI.

Wraps the ConfidentAPIClient so pipeline scripts can sync goldens and
quality artifacts to the Confident AI cloud in a single call.

Usage:
    # Push a golden JSONL to Confident AI
    from src.core.ops.confident_push import push_goldens_if_confident, is_confident_enabled
    if is_confident_enabled():
        push_goldens_if_confident("goldens.jsonl", alias="npc-goldens-history_guide-template")

    # CLI
    python scripts/ops/confident_push.py push goldens.jsonl --alias "npc-goldens-template"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.core.ops.confident_api import (
    ConfidentAPIClient,
    confident_available as api_key_available,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_client() -> ConfidentAPIClient:
    """Get a configured ConfidentAPIClient.

    Raises
    ------
    EnvironmentError
        If ``CONFIDENT_API_KEY`` is not set in the environment.
    """
    return ConfidentAPIClient()


def is_confident_enabled() -> bool:
    """Return True if a Confident AI API key is available (env or .env.local)."""
    try:
        from deepeval.confident.api import is_confident

        return is_confident()
    except ImportError:
        return False
    except (ConnectionError, TimeoutError, OSError):
        return False


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------


def push_goldens_if_confident(
    jsonl_path: str,
    alias: str | None = None,
    version: str | None = None,
    finalized: bool = True,
    turn_type: str = "single",
) -> bool:
    """Push goldens from a JSONL/JSON file to Confident AI as a named dataset.

    Parameters
    ----------
    jsonl_path
        Path to a JSONL file (one golden dict per line) or a JSON file
        (a single array of golden dicts).
    alias
        Dataset alias on Confident AI.  Derived from the filename stem
        when omitted.
    version
        Optional semantic version string (e.g. ``"1.0.0"``).
    finalized
        Whether pushed goldens should be finalized/eval-ready. Use False for
        generated candidates queued for Confident review.
    turn_type
        ``single`` for Golden payloads or ``conversation`` for ConversationalGolden payloads.

    Returns
    -------
    bool
        ``True`` on success, ``False`` if not authenticated or the push
        failed.
    """
    path = Path(jsonl_path)
    if not path.exists():
        print(f"[confident_push] Skipping: {jsonl_path} does not exist.")
        return False

    if not is_confident_enabled():
        print("[confident_push] Confident AI not enabled — skipping cloud push.")
        return False

    if alias is None:
        alias = path.stem

    # ---- Parse goldens from file -------------------------------------------
    goldens: list[dict] = []
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            print(f"[confident_push] Empty file: {jsonl_path}")
            return False

        if path.suffix == ".json":
            data = json.loads(raw)
            if isinstance(data, list):
                goldens = data
            else:
                goldens = [data]
        else:
            # JSONL — one golden dict per line
            for line in raw.split("\n"):
                line = line.strip()
                if line:
                    goldens.append(json.loads(line))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[confident_push] Failed to read goldens from {jsonl_path}: {exc}")
        return False

    if not goldens:
        print(f"[confident_push] No goldens found in {jsonl_path}.")
        return False

    # ---- Push via API client ------------------------------------------------
    try:
        client = get_client()
        print(
            f"[confident_push] Pushing {len(goldens)} goldens "
            f"\u2192 alias='{alias}' ..."
        )
        if turn_type in {"conversation", "conversational", "multi"}:
            client.push_dataset(
                alias,
                conversational_goldens=goldens,
                version=version,
                finalized=finalized,
            )
        else:
            client.push_dataset(alias, goldens, version=version, finalized=finalized)
        print(f"[confident_push] \u2713 Pushed to Confident AI as '{alias}'.")
        return True
    except Exception as exc:
        print(f"[confident_push] Push failed (non-fatal): {exc}")
        return False


def pull_goldens(alias: str) -> list[dict]:
    """Pull a dataset from Confident AI by alias.

    Parameters
    ----------
    alias
        Dataset alias on Confident AI.

    Returns
    -------
    list[dict]
        The list of golden dicts.  Empty if the pull failed.

    Raises
    ------
    RuntimeError
        If ``CONFIDENT_API_KEY`` is not configured.
    """
    if not is_confident_enabled():
        raise RuntimeError(
            "CONFIDENT_API_KEY is not set. "
            "Set it in .env.local or export CONFIDENT_API_KEY=..."
        )

    try:
        client = get_client()
        goldens = client.pull_dataset(alias)
        print(
            f"[confident_push] Pulled {len(goldens)} goldens from '{alias}'."
        )
        return goldens
    except Exception as exc:
        print(f"[confident_push] Pull failed: {exc}")
        return []


def list_datasets() -> list[dict]:
    """List all datasets on Confident AI.

    Returns
    -------
    list[dict]
        Raw dataset metadata list.  Empty on error.
    """
    try:
        client = get_client()
        datasets = client.list_datasets()
        print(f"{'Name':<40} {'Alias':<40} {'Version':<12} {'Goldens':<8}")
        print("-" * 100)
        for ds in datasets:
            name = ds.get("name", ds.get("dataset_name", ""))
            alias = ds.get("alias", ds.get("dataset_alias", ""))
            version = ds.get("version", "-")
            count = ds.get(
                "golden_count",
                ds.get("goldens_count", ds.get("total_goldens", 0)),
            )
            print(
                f"{str(name)[:38]:<40} "
                f"{str(alias)[:38]:<40} "
                f"{str(version)[:10]:<12} "
                f"{count:<8}"
            )
        return datasets
    except Exception as exc:
        print(f"[confident_push] Failed to list datasets: {exc}")
        return []


def list_test_runs(page: int = 1, page_size: int = 20) -> list[dict]:
    """List test runs from Confident AI.

    Parameters
    ----------
    page
        Page number (1-indexed).
    page_size
        Items per page.

    Returns
    -------
    list[dict]
        The list of test-run dicts for the requested page.  Empty on error.
    """
    try:
        client = get_client()
        result = client.list_test_runs_paginated(page, page_size)
        items = result.get(
            "items", result.get("data", result.get("testRuns", []))
        )
        total = result.get("total", len(items))
        print(
            f"Test Runs (page {page}, "
            f"{page_size} per page, {total} total):"
        )
        header = (
            f"{'ID':<40} {'Identifier':<50} {'Pass':<8} "
            f"{'Total':<8} {'Status':<12} {'Date':<20}"
        )
        print(header)
        print("-" * len(header))
        for run in items:
            run_id = run.get("test_run_id", run.get("id", ""))
            identifier = run.get("identifier", run.get("name", ""))
            passed = run.get("passed_count", run.get("passed", 0))
            total_count = run.get("total_count", run.get("total", 0))
            status = run.get("status", run.get("state", "-"))
            date = (
                run.get("created_at", run.get("date", run.get("timestamp", "")))
            )[:19]
            print(
                f"{str(run_id)[:38]:<40} "
                f"{str(identifier)[:48]:<50} "
                f"{passed:<8} "
                f"{total_count:<8} "
                f"{str(status)[:10]:<12} "
                f"{date:<20}"
            )
        return items
    except Exception as exc:
        print(f"[confident_push] Failed to list test runs: {exc}")
        return []


def get_test_run(test_run_id: str) -> dict:
    """Get a test run by ID from Confident AI.

    Parameters
    ----------
    test_run_id
        The UUID of the test run.

    Returns
    -------
    dict
        Test-run data.  Empty dict on error.
    """
    try:
        client = get_client()
        run = client.get_test_run(test_run_id)
        print(f"Test Run: {test_run_id}")
        print(json.dumps(run, indent=2, default=str))
        return run
    except Exception as exc:
        print(
            f"[confident_push] Failed to get test run "
            f"'{test_run_id}': {exc}"
        )
        return {}


# ---------------------------------------------------------------------------
# Alias builder (kept for backwards compatibility)
# ---------------------------------------------------------------------------


def _build_alias(
    npc_key: str, technique: str, prefix: str = "npc-goldens", turn_type: str | None = None
) -> str:
    """Build a standardised Confident AI dataset alias from NPC metadata."""
    if prefix == "ucore":
        npc_slug = npc_key.replace("_", "-")
        suffix = "conversation-v1" if turn_type in {"conversation", "conversational", "multi"} else "single-v1"
        return f"ucore-{npc_slug}-{technique}-{suffix}"
    return f"{prefix}-{npc_key}-{technique}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push/pull NPC golden datasets to/from Confident AI"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    push_p = sub.add_parser(
        "push", help="Push a local goldens file to Confident AI"
    )
    push_p.add_argument(
        "jsonl_path", help="Path to JSONL/JSON goldens file"
    )
    push_p.add_argument(
        "--alias",
        default=None,
        help="Dataset alias (derived from filename if omitted)",
    )
    push_p.add_argument(
        "--version", default=None, help="Optional semantic version string"
    )
    push_p.add_argument(
        "--turn-type",
        choices=["single", "conversation"],
        default="single",
        help="Confident payload type: single -> goldens, conversation -> conversationalGoldens",
    )
    final_group = push_p.add_mutually_exclusive_group()
    final_group.add_argument("--finalized", dest="finalized", action="store_true", default=True, help="Mark pushed goldens finalized/eval-ready")
    final_group.add_argument("--unfinalized", dest="finalized", action="store_false", help="Queue pushed goldens for Confident review")

    pull_p = sub.add_parser(
        "pull", help="Pull a dataset from Confident AI"
    )
    pull_p.add_argument("alias", help="Confident AI dataset alias")

    list_ds_p = sub.add_parser(
        "list-datasets", help="List all datasets on Confident AI"
    )
    _ = list_ds_p  # no extra args needed

    list_tr_p = sub.add_parser(
        "list-test-runs", help="List test runs from Confident AI"
    )
    list_tr_p.add_argument(
        "--page", type=int, default=1, help="Page number (1-indexed)"
    )
    list_tr_p.add_argument(
        "--page-size", type=int, default=20, help="Items per page"
    )

    get_tr_p = sub.add_parser(
        "get-test-run", help="Get a test run by ID"
    )
    get_tr_p.add_argument("test_run_id", help="Test run UUID")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.cmd == "push":
        ok = push_goldens_if_confident(
            args.jsonl_path,
            alias=args.alias,
            version=args.version,
            finalized=args.finalized,
            turn_type=args.turn_type,
        )
        sys.exit(0 if ok else 1)

    elif args.cmd == "pull":
        goldens = pull_goldens(args.alias)
        if goldens:
            print(json.dumps(goldens[:3], indent=2))
            if len(goldens) > 3:
                print(f"  ... and {len(goldens) - 3} more goldens.")
        sys.exit(0 if goldens else 1)

    elif args.cmd == "list-datasets":
        datasets = list_datasets()
        sys.exit(0 if datasets else 1)

    elif args.cmd == "list-test-runs":
        runs = list_test_runs(args.page, args.page_size)
        sys.exit(0 if runs else 1)

    elif args.cmd == "get-test-run":
        run_data = get_test_run(args.test_run_id)
        sys.exit(0 if run_data else 1)


if __name__ == "__main__":
    main()
