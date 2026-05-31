#!/usr/bin/env python3
"""Push local NPC evaluation datasets to Confident AI.

Wraps the DeepEval EvaluationDataset push/pull API so pipeline scripts
can sync goldens and quality artifacts to the Confident AI cloud in a
single call.

Usage:
    # Push a golden JSON to Confident AI
    from scripts.ops.confident_push import push_goldens_if_confident, is_confident_enabled
    if is_confident_enabled():
        push_goldens_if_confident(golden_path, alias="npc-goldens-history_guide-template")

    # CLI
    python scripts/ops/confident_push.py tests/evals/.dataset/npc_goldens_template.json \
        --alias "npc-goldens-template"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def is_confident_enabled() -> bool:
    """Return True if a Confident AI API key is available (env or .env.local)."""
    try:
        from deepeval.confident.api import is_confident
        return is_confident()
    except ImportError:
        return False
    except (ConnectionError, TimeoutError, OSError):
        return False


def push_goldens_if_confident(
    golden_path: Path | str,
    *,
    alias: str,
    overwrite: bool = True,
    verbose: bool = True,
) -> bool:
    """Push a local golden JSON file to Confident AI as a named dataset.

    Args:
        golden_path: Path to a local golden JSON file (EvaluationDataset format).
        alias:       Dataset alias on Confident AI (used for pull too).
        overwrite:   Overwrite the remote dataset if it already exists.
        verbose:     Print progress messages.

    Returns:
        True on success, False if not authenticated or push failed.
    """
    golden_path = Path(golden_path)
    if not golden_path.exists():
        if verbose:
            print(f"[confident_push] Skipping: {golden_path} does not exist.")
        return False

    if not is_confident_enabled():
        if verbose:
            print("[confident_push] CONFIDENT_API_KEY not set — skipping cloud push.")
        return False

    try:
        from deepeval.dataset import EvaluationDataset
        dataset = EvaluationDataset()
        dataset.add_goldens_from_json_file(file_path=str(golden_path))
        if verbose:
            print(f"[confident_push] Pushing {len(dataset.goldens)} goldens → alias='{alias}' ...")
        dataset.push(alias=alias)
        if verbose:
            print(f"[confident_push] ✓ Pushed to Confident AI as '{alias}'.")
        return True
    except Exception as exc:
        if verbose:
            print(f"[confident_push] Push failed (non-fatal): {exc}")
        return False


def pull_goldens(alias: str, *, output_path: Path | str | None = None, verbose: bool = True) -> list[dict]:
    """Pull a golden dataset from Confident AI by alias.

    Returns the list of goldens (dicts). Optionally writes them to output_path.
    """
    if not is_confident_enabled():
        raise RuntimeError(
            "CONFIDENT_API_KEY is not set. Set it in .env.local or export CONFIDENT_API_KEY=..."
        )

    from deepeval.dataset import EvaluationDataset
    dataset = EvaluationDataset()
    dataset.pull(alias=alias)
    if verbose:
        print(f"[confident_push] Pulled {len(dataset.goldens)} goldens from '{alias}'.")

    goldens_as_dicts: list[dict] = []
    for g in dataset.goldens:
        goldens_as_dicts.append(
            {
                "input": g.input,
                "actual_output": g.actual_output or "",
                "expected_output": g.expected_output or "",
                "context": list(g.context or []),
                "retrieval_context": list(g.retrieval_context or []),
                "metadata": g.additional_metadata or {},
                "tags": list(g.custom_column_data.get("tags", []) if hasattr(g, "custom_column_data") else []),
            }
        )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(goldens_as_dicts, f, indent=2, ensure_ascii=False)
            f.write("\n")
        if verbose:
            print(f"[confident_push] Saved to {output_path}")

    return goldens_as_dicts


def _build_alias(npc_key: str, technique: str, prefix: str = "npc-goldens") -> str:
    return f"{prefix}-{npc_key}-{technique}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push/pull NPC golden datasets to/from Confident AI"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    push_p = sub.add_parser("push", help="Push a local golden JSON to Confident AI")
    push_p.add_argument("golden_path", help="Path to golden JSON file")
    push_p.add_argument("--alias", required=True, help="Confident AI dataset alias")
    push_p.add_argument("--no-overwrite", action="store_true", help="Do not overwrite if alias exists")

    pull_p = sub.add_parser("pull", help="Pull a golden dataset from Confident AI")
    pull_p.add_argument("alias", help="Confident AI dataset alias")
    pull_p.add_argument("--output", default=None, help="Save pulled goldens to this JSON path")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.cmd == "push":
        ok = push_goldens_if_confident(
            args.golden_path,
            alias=args.alias,
            overwrite=not args.no_overwrite,
        )
        sys.exit(0 if ok else 1)

    elif args.cmd == "pull":
        goldens = pull_goldens(args.alias, output_path=args.output)
        if not args.output:
            print(json.dumps(goldens[:3], indent=2))
            if len(goldens) > 3:
                print(f"  ... and {len(goldens) - 3} more goldens.")
        sys.exit(0)


if __name__ == "__main__":
    main()
