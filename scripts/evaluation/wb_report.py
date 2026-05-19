#!/usr/bin/env python3
"""
wb_report.py — Generate portfolio-ready evaluation report from W&B data.

Connects to W&B, fetches the latest eval runs for each NPC, and produces a
polished markdown report that can be shared with employers or published.

Usage:
    python scripts/evaluation/wb_report.py                       # Latest eval for each NPC
    python scripts/evaluation/wb_report.py --npc history_guide   # Specific NPC
    python scripts/evaluation/wb_report.py --run-id <run_id>      # Specific W&B run
    python scripts/evaluation/wb_report.py --output my_report.md  # Custom path

Requires:
    wandb.login() already configured (via ~/.netrc or env)
    WANDB_ENTITY and WANDB_PROJECT can be set in environment
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts._repo_root import PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))


def active_npc_keys():
    """Return currently active NPC keys from subjects/NPC_specs/*.json."""
    keys = []
    for path in sorted((PROJECT_ROOT / "subjects").glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                spec = json.load(f)
            keys.append(spec.get("npc_key") or path.stem)
        except Exception:
            keys.append(path.stem)
    return set(keys)


def fetch_eval_runs(entity, project, npc_key=None, limit=3, active_only=True):
    """Fetch the most recent W&B eval runs."""
    import wandb

    api = wandb.Api()
    filters = {"tags": "eval"}
    if npc_key:
        filters["tags"] = {"$in": ["eval", npc_key]}
        filters["config.npc_key"] = npc_key
    try:
        runs = list(api.runs(f"{entity}/{project}", filters=filters, per_page=limit))
    except Exception as e:
        print(f"Error fetching runs: {e}")
        # Fall back: just get any runs with eval tag
        try:
            runs = [r for r in api.runs(f"{entity}/{project}", per_page=limit) if "eval" in (r.tags or [])]
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
            return []

    if active_only and not npc_key:
        active_keys = active_npc_keys()
        runs = [r for r in runs if r.config.get("npc_key") in active_keys]
    return runs[:limit]


def format_win_rate(win_rate, total):
    """Color-code win rate."""
    stars = ""
    if win_rate >= 0.8:
        stars = " ⭐ (Excellent)"
    elif win_rate >= 0.6:
        stars = " 👍 (Good)"
    elif win_rate >= 0.4:
        stars = " (Average)"
    else:
        stars = " ⚠️ (Needs improvement)"
    return f"{win_rate:.0%} ({win_rate * total:.0f}/{total}){stars}"


def generate_report(entity, project, runs, output_path=None):
    """Generate a portfolio-ready markdown report from W&B runs."""
    from collections import defaultdict

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []

    lines.append("# Unsloth_Core NPC Evaluation Report\n")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Source:** [W&B Project](https://wandb.ai/{entity}/{project})")
    lines.append("")
    lines.append("---\n")
    lines.append("## Executive Summary\n")
    lines.append(
        "This report summarizes the evaluation results of fine-tuned NPC dialogue models "
        "trained using the Unsloth_Core pipeline. Each NPC is a Llama 3.2 3B Instruct model "
        "fine-tuned with LoRA on synthetic datasets generated via template/Ollama.\n"
    )

    # Group runs by NPC
    by_npc = defaultdict(list)
    for run in runs:
        npc_key = run.config.get("npc_key", "unknown")
        by_npc[npc_key].append(run)

    for npc_key, npc_runs in sorted(by_npc.items()):
        lines.append(f"---\n")
        lines.append(f"## NPC: {npc_key}\n")
        for run in sorted(npc_runs, key=lambda r: r.created_at, reverse=True):
            run_name = run.name or "unnamed"
            created = run.created_at.split(".")[0] if run.created_at else "unknown"
            win_rate = run.summary.get("eval/win_rate", 0)
            total = run.summary.get("eval/total", 0)
            cw = run.summary.get("eval/candidate_wins", 0)
            bw = run.summary.get("eval/baseline_wins", 0)
            ties = run.summary.get("eval/ties", 0)
            baseline = run.config.get("baseline", "unknown")
            candidate = run.config.get("candidate", "unknown")

            lines.append(f"### Run: {run_name}")
            lines.append(f"| Metric | Value |")
            lines.append(f"|--------|-------|")
            lines.append(f"| Run ID | [`{run.id}`](https://wandb.ai/{entity}/{project}/runs/{run.id}) |")
            lines.append(f"| Date | {created} |")
            lines.append(f"| Baseline | {baseline} |")
            lines.append(f"| Candidate | {candidate} |")
            lines.append(f"| Total questions | {total} |")
            lines.append(f"| Candidate wins | {cw}/{total} |")
            lines.append(f"| Baseline wins | {bw}/{total} |")
            lines.append(f"| Ties | {ties} |")
            lines.append(f"| Win rate | {format_win_rate(win_rate, total)} |")
            lines.append("")

            # Category breakdown if available
            category_keys = [k for k in run.summary.keys() if k.startswith("eval/category/")]
            if category_keys:
                lines.append("#### Category Breakdown\n")
                lines.append("| Category | Win Rate | Wins/Total |")
                lines.append("|----------|----------|------------|")
                for key in sorted(category_keys):
                    parts = key.split("/")
                    if len(parts) >= 3:
                        cat = parts[2]
                        val = run.summary[key]
                        if "win_rate" in key:
                            cat_total_key = f"eval/category/{cat}/total"
                            cat_wins_key = f"eval/category/{cat}/wins"
                            cat_total = run.summary.get(cat_total_key, 0)
                            cat_wins = run.summary.get(cat_wins_key, 0)
                            lines.append(f"| {cat} | {val:.0%} | {cat_wins}/{cat_total} |")
                lines.append("")

            # W&B Table link
            lines.append(f"**W&B Run:** [Open in W&B](https://wandb.ai/{entity}/{project}/runs/{run.id})")
            lines.append("")

    lines.append("---\n")
    lines.append("## Methodology\n")
    lines.append("""
- **Base model:** [Llama 3.2 3B Instruct](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct)
- **Fine-tuning:** LoRA adapters trained with Unsloth
- **Dataset:** 64-72 synthetic ChatML examples per NPC, generated via template/Ollama
- **Evaluation:** Side-by-side comparison using llama.cpp server
  - Heuristic scoring: sentence count, name adherence, AI disclaimer avoidance, lexical diversity
  - Per-category breakdown by NPC role (identity, teaching, dialogue, quest, refusal)
- **Export:** Adapter-only GGUF (~50 MB per NPC) for Unity/LLMUnity runtime
""")

    lines.append("---\n")
    lines.append(f"*Report generated by `wb_report.py` via W&B API*")

    report = "\n".join(lines)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            f.write(report)
        print(f"Report saved to: {out.resolve()}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate W&B evaluation report")
    parser.add_argument("--npc", help="Specific NPC key to report on")
    parser.add_argument("--run-id", help="Specific W&B run ID")
    parser.add_argument("--output", "-o", help="Output markdown path")
    parser.add_argument("--limit", type=int, default=5, help="Max runs to fetch (default: 5)")
    args = parser.parse_args()

    entity = os.environ.get("WANDB_ENTITY", "andreabenathar-twl-games")
    project = os.environ.get("WANDB_PROJECT", "unsloth-core")

    if args.run_id:
        import wandb
        api = wandb.Api()
        run = api.run(f"{entity}/{project}/{args.run_id}")
        runs = [run]
    else:
        runs = fetch_eval_runs(entity, project, npc_key=args.npc, limit=args.limit)

    if not runs:
        print("No W&B eval runs found.")
        print(f"Checked: entity={entity}, project={project}")
        print("Make sure you've run `./ucore evaluate --wandb` at least once.")
        sys.exit(1)

    output = args.output or f"eval/reports/wandb_report_{datetime.now().strftime('%Y%m%d')}.md"
    report = generate_report(entity, project, runs, output_path=output)

    print("\n" + report)


if __name__ == "__main__":
    main()
