#!/usr/bin/env python3
"""Import PeerLM evaluation results into Weights & Biases."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# Mapping from display names in run names to NPC keys
_NPC_NAME_MAP = {
    "HistoryGuide": "history_guide",
    "ChefAssistant": "chef_assistant",
}


def detect_npc_key(run_name: str) -> str | None:
    """Extract NPC key from a PeerLM run name.

    Expected patterns: "Unsloth_Core HistoryGuide ...", "Unsloth_Core ChefAssistant ..."
    """
    if not run_name:
        return None
    for display_name, npc_key in _NPC_NAME_MAP.items():
        if display_name in run_name:
            return npc_key
    match = re.search(r"Unsloth_Core\s+(\S+)", run_name)
    if match:
        return match.group(1).lower()
    return None


def load_peerlm_result(path: Path) -> dict:
    """Load and validate a PeerLM result JSON file.

    Parses at the boundary: returns a trusted dict with guaranteed run.resultsSummary key.
    """
    if not path.exists():
        print(f"Error: input file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)

    run = data.get("run")
    if run is None:
        print(f"Error: missing 'run' key in {path}", file=sys.stderr)
        sys.exit(1)

    if "resultsSummary" not in run:
        print(f"Error: missing 'resultsSummary' in run data", file=sys.stderr)
        sys.exit(1)

    return data


def build_leaderboard_table(overall: list[dict]) -> "wandb.Table":
    """Build a W&B Table from the overall leaderboard entries.

    Columns: model, rank, overall_score, total_cost_usd, plus one column per criteria.
    """
    import wandb

    # Collect all unique criteria keys across all entries
    criteria_keys: set[str] = set()
    for entry in overall:
        criteria_keys.update(entry.get("criteriaScores", {}).keys())
    sorted_criteria = sorted(criteria_keys)

    columns = ["model", "rank", "overall_score", "total_cost_usd", "response_count"]
    columns += sorted_criteria

    table = wandb.Table(columns=columns)
    for entry in overall:
        scores = entry.get("criteriaScores", {})
        row = [
            entry.get("modelId", "?"),
            entry.get("rank", 0),
            entry.get("overallScore", 0),
            entry.get("totalCostUsd", 0),
            entry.get("responseCount", 0),
        ]
        row += [scores.get(k, 0) for k in sorted_criteria]
        table.add_data(*row)
    return table


def _safe_id(model_id: str) -> str:
    """Convert a model ID like 'qwen/qwen3-30b-a3b' to a safe W&B metric prefix."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", model_id)


def _parse_timestamp(iso_string: str) -> str:
    """Convert ISO timestamp to YYYYMMDD-HHMM for run naming.

    Returns empty string on any parse failure.
    """
    if not iso_string:
        return ""
    try:
        from datetime import datetime as _dt

        parsed = _dt.fromisoformat(iso_string.replace("Z", "+00:00"))
        return parsed.strftime("%Y%m%d-%H%M")
    except (ValueError, TypeError):
        return ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(
        description="Import PeerLM evaluation results into Weights & Biases."
    )
    ap.add_argument(
        "--input",
        required=True,
        help="Path to the PeerLM result JSON file",
    )
    ap.add_argument(
        "--wandb-project",
        default="unsloth-core",
        help="W&B project name (default: unsloth-core)",
    )
    ap.add_argument(
        "--wandb-entity",
        default="andreabenathar-twl-games",
        help="W&B entity name (default: andreabenathar-twl-games)",
    )
    ap.add_argument(
        "--npc-key",
        default=None,
        help="NPC key (auto-detected from run name if omitted)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be logged without creating W&B runs",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)

    # --- Parse input at boundary ---
    data = load_peerlm_result(input_path)
    run_info = data["run"]
    summary = run_info["resultsSummary"]
    overall = summary.get("overall", [])

    # --- Early exit: no leaderboard data ---
    if not overall:
        print("Error: no entries in resultsSummary.overall", file=sys.stderr)
        return 1

    # --- Auto-detect NPC key ---
    npc_key = args.npc_key or detect_npc_key(run_info.get("name", ""))
    if npc_key is None:
        print(
            "Error: could not auto-detect NPC key from run name. "
            "Provide --npc-key explicitly.",
            file=sys.stderr,
        )
        return 1

    # --- Extract metadata ---
    suite_name = run_info.get("name", "Unknown")
    completed_at = run_info.get("completedAt", "")
    credits_consumed = run_info.get("evalCreditsConsumed", 0)
    credits_cached = run_info.get("evalCreditsCached", 0)

    print(f"Importing PeerLM results for NPC: {npc_key}")
    print(f"  Suite: {suite_name}")
    print(f"  Completed: {completed_at}")
    print(f"  Models: {[e['modelId'] for e in overall]}")
    print(f"  Credits consumed: {credits_consumed} (cached: {credits_cached})")

    # --- Dry-run: preview only ---
    if args.dry_run:
        print("\n[Dry-run] Would log the following to W&B:")
        print(f"  Project: {args.wandb_project}")
        print(f"  Entity: {args.wandb_entity}")
        print(f"  Tags: peerlm, {npc_key}")
        for entry in overall:
            scores = entry.get("criteriaScores", {})
            print(
                f"  {entry.get('modelId', '?')}: "
                f"rank={entry.get('rank', '?')}, "
                f"overall={entry.get('overallScore', '?')}, "
                f"cost=${entry.get('totalCostUsd', 0):.6f}",
            )
            for criterion, val in scores.items():
                print(f"    {criterion}: {val}")
        return 0

    # --- Import wandb (fail fast if unavailable) ---
    try:
        import wandb
    except ImportError:
        print(
            "Error: wandb is not installed. Install with: pip install wandb",
            file=sys.stderr,
        )
        return 1

    # --- Build run name ---
    stamp = _parse_timestamp(completed_at)
    run_name = f"peerlm-{npc_key}-{stamp}" if stamp else f"peerlm-{npc_key}"

    # --- Initialize W&B run ---
    wandb.init(
        project=args.wandb_project,
        entity=args.wandb_entity,
        name=run_name,
        config={
            "npc_key": npc_key,
            "suite_name": suite_name,
            "peerlm_run_id": run_info.get("id", ""),
            "completed_at": completed_at,
            "eval_credits_consumed": credits_consumed,
            "eval_credits_cached": credits_cached,
            "evaluation_method": summary.get("evaluationMethod", ""),
            "total_evaluations": summary.get("totalEvaluations", 0),
            "total_responses": summary.get("totalResponses", 0),
            "model_count": len(overall),
        },
        tags=["peerlm", npc_key],
    )

    # --- Log leaderboard table ---
    table = build_leaderboard_table(overall)
    wandb.log({"peerlm/leaderboard": table})

    # --- Log per-model metrics as summary ---
    for entry in overall:
        model_id = entry.get("modelId", "unknown")
        sid = _safe_id(model_id)
        crit = entry.get("criteriaScores", {})

        # Per-model summary values (fixed, not time-series)
        wandb.summary[f"models/{sid}/rank"] = entry.get("rank", 0)
        wandb.summary[f"models/{sid}/overall_score"] = entry.get("overallScore", 0)
        wandb.summary[f"models/{sid}/total_cost_usd"] = entry.get("totalCostUsd", 0)
        wandb.summary[f"models/{sid}/response_count"] = entry.get("responseCount", 0)
        wandb.summary[f"models/{sid}/avg_latency_ms"] = entry.get("avgLatencyMs", 0)
        wandb.summary[f"models/{sid}/avg_prompt_tokens"] = entry.get("avgPromptTokens", 0)
        wandb.summary[f"models/{sid}/avg_completion_tokens"] = entry.get("avgCompletionTokens", 0)
        wandb.summary[f"models/{sid}/total_prompt_tokens"] = entry.get("totalPromptTokens", 0)
        wandb.summary[f"models/{sid}/total_completion_tokens"] = entry.get("totalCompletionTokens", 0)

        # Per-criteria scores as summary
        for criterion, val in crit.items():
            safe_key = _safe_id(criterion.lower().replace(" ", "_"))
            wandb.summary[f"models/{sid}/criteria/{safe_key}"] = val

    # --- Log credit usage ---
    wandb.log({
        "credits/consumed": credits_consumed,
        "credits/cached": credits_cached,
        "credits/total": credits_consumed + credits_cached,
    })

    wandb.finish()
    print(f"W&B run '{run_name}' logged successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
