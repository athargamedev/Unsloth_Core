#!/usr/bin/env python3
"""
compare_runs.py — Compare two or more training runs for the same NPC.

Extracts TensorBoard metrics and produces a markdown comparison report.

Usage:
    python scripts/compare_runs.py outputs/chemistry_instructor/runs/20260512_fast-3b_001 outputs/chemistry_instructor/runs/20260512_quality-1.7b_001
    
    # Compare all runs for an NPC
    python scripts/compare_runs.py outputs/chemistry_instructor/runs/*
    
    # Spec output path
    python scripts/compare_runs.py outputs/chemistry_instructor/runs/run_1 outputs/chemistry_instructor/runs/run_2 --output eval/comparisons/chemistry_vs_comparison.md
"""

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths


def extract_metrics(run_dir: Path) -> dict | None:
    """Extract training/eval metrics from a run directory.
    
    Reads metrics.json first (frozen by train.py).
    Falls back to parsing TensorBoard event files.
    Returns None if no metrics found.
    """
    metrics_file = run_dir / "metrics.json"
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics = json.load(f)
        # Calculate perplexity if we have eval loss
        eval_loss = metrics.get("eval_loss")
        if eval_loss is not None and eval_loss > 0:
            metrics["eval_perplexity"] = round(math.exp(eval_loss), 2)
        training_loss = metrics.get("training_loss")
        if training_loss is not None and training_loss > 0:
            metrics["training_perplexity"] = round(math.exp(training_loss), 2)
        return metrics
    
    # Fallback: parse TensorBoard events if no metrics.json
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
        
        event_files = list(run_dir.glob("events.out.tfevents.*"))
        if not event_files:
            return None
        
        ea = EventAccumulator(str(run_dir))
        ea.Reload()
        
        metrics = {
            "run_id": run_dir.name,
            "steps": {},
        }
        
        for tag in ea.Tags().get("scalars", []):
            events = ea.Scalars(tag)
            if events:
                metrics["steps"][tag] = {
                    "final": round(events[-1].value, 4),
                    "best": round(min(e.value for e in events), 4),
                    "count": len(events),
                }
                if tag in ("eval/loss", "loss") and events[-1].value > 0:
                    metrics["steps"][f"{tag}_perplexity"] = round(math.exp(events[-1].value), 2)
        
        return metrics
    except ImportError:
        print("Warning: tensorboard not installed, cannot parse event files")
        return None


def generate_comparison_report(runs: list[dict], output_path: str | None = None) -> str:
    """Generate a markdown comparison report."""
    lines = []
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    lines.append("# Training Run Comparison\n")
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Runs compared:** {len(runs)}\n")
    
    # Summary table
    lines.append("## Overview\n")
    lines.append("| Metric | " + " | ".join(r.get("run_id", f"Run {i}") for i, r in enumerate(runs)) + " |")
    lines.append("|" + "---|" * (len(runs) + 1))
    
    # Training loss
    train_losses = [r.get("training_loss") for r in runs]
    if any(tl is not None for tl in train_losses):
        row = "| Training Loss |"
        for tl in train_losses:
            row += f" {tl:.4f} |" if tl is not None else " — |"
        lines.append(row)
    
    # Training perplexity
    train_perps = [r.get("training_perplexity") for r in runs]
    if any(tp is not None for tp in train_perps):
        row = "| Training Perplexity |"
        for tp in train_perps:
            row += f" {tp:.2f} |" if tp is not None else " — |"
        lines.append(row)
    
    # Eval loss
    eval_losses = [r.get("eval_loss") for r in runs]
    if any(el is not None for el in eval_losses):
        row = "| Eval Loss |"
        for el in eval_losses:
            row += f" {el:.4f} |" if el is not None else " — |"
        lines.append(row)
    
    # Eval perplexity
    eval_perps = [r.get("eval_perplexity") for r in runs]
    if any(ep is not None for ep in eval_perps):
        row = "| Eval Perplexity |"
        for ep in eval_perps:
            row += f" {ep:.2f} |" if ep is not None else " — |"
        lines.append(row)
    
    # Preset
    presets = [r.get("preset", "") for r in runs]
    if any(p for p in presets):
        row = "| Preset |"
        for p in presets:
            row += f" {p} |" if p else " — |"
        lines.append(row)
    
    # Model
    models = [r.get("model", "") for r in runs]
    if any(m for m in models):
        row = "| Model |"
        for m in models:
            row += f" {m} |" if m else " — |"
        lines.append(row)
    
    # Epochs/Steps from config if available
    configs = [r.get("config", {}) for r in runs]
    epochs = [c.get("num_epochs") if isinstance(c, dict) else None for c in configs]
    if any(e is not None for e in epochs):
        row = "| Epochs |"
        for e in epochs:
            row += f" {e} |" if e is not None else " — |"
        lines.append(row)
    
    lines.append("")
    
    # Per-run details
    lines.append("## Run Details\n")
    for i, run in enumerate(runs):
        lines.append(f"### Run {i+1}: {run.get('run_id', 'unknown')}\n")
        lines.append(f"- **Preset:** {run.get('preset', 'N/A')}")
        lines.append(f"- **Model:** {run.get('model', 'N/A')}")
        if run.get("config"):
            c = run["config"]
            lines.append(f"- **Epochs:** {c.get('num_epochs', 'N/A')}, **LR:** {c.get('learning_rate', 'N/A')}")
            lines.append(f"- **Batch:** {c.get('batch_size', 'N/A')}, **Grad Accum:** {c.get('gradient_accumulation_steps', 'N/A')}")
            lines.append(f"- **LoRA r:** {c.get('lora_r', 'N/A')}, **alpha:** {c.get('lora_alpha', 'N/A')}")
        lines.append("")
    
    # TensorBoard step-level detail if available
    has_steps = any("steps" in r for r in runs)
    if has_steps:
        lines.append("## Step-by-Step Metrics\n")
        for i, run in enumerate(runs):
            steps = run.get("steps", {})
            if not steps:
                continue
            lines.append(f"### Run {i+1}: {run.get('run_id', 'unknown')}\n")
            for tag, data in steps.items():
                lines.append(f"- **{tag}:** final={data.get('final', 'N/A')}, "
                             f"best={data.get('best', 'N/A')}, steps={data.get('count', 'N/A')}")
                if f"{tag}_perplexity" in steps:
                    lines.append(f"  → perplexity: {steps[f'{tag}_perplexity']}")
            lines.append("")
    
    # Recommendations
    lines.append("## Recommendations\n")
    if eval_losses and all(el is not None for el in eval_losses):
        best_idx = eval_losses.index(min(eval_losses))
        lines.append(f"- **Best eval loss:** Run {best_idx+1} ({runs[best_idx].get('run_id', 'unknown')}) "
                     f"with {eval_losses[best_idx]:.4f}")
    if train_losses and all(tl is not None for tl in train_losses):
        best_train_idx = train_losses.index(min(train_losses))
        if best_train_idx != (best_idx if eval_losses and all(el is not None for el in eval_losses) else -1):
            lines.append(f"- **Best training loss:** Run {best_train_idx+1} "
                         f"({runs[best_train_idx].get('run_id', 'unknown')})")
    
    report = "\n".join(lines)
    
    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            f.write(report)
        print(f"Report saved to: {output}")
    else:
        print(report)
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Compare training runs for an NPC")
    parser.add_argument("runs", nargs="+", help="Run directories to compare")
    parser.add_argument("--output", "-o", help="Output markdown path (default: auto in eval/comparisons/)")
    args = parser.parse_args()
    
    if len(args.runs) < 2:
        print("Error: At least two run directories are required for comparison.")
        sys.exit(1)
    
    # Resolve run directories
    run_dirs = []
    for r in args.runs:
        p = Path(r)
        if not p.exists():
            print(f"Error: Run directory not found: {p}")
            sys.exit(1)
        run_dirs.append(p)
    
    print(f"Comparing {len(run_dirs)} runs...\n")
    
    # Extract metrics from each run
    runs = []
    for rd in run_dirs:
        metrics = extract_metrics(rd)
        if metrics:
            runs.append(metrics)
            rid = metrics.get("run_id", rd.name)
            train_loss = metrics.get("training_loss")
            eval_loss = metrics.get("eval_loss")
            print(f"  {rid}: train_loss={train_loss}, eval_loss={eval_loss}")
        else:
            print(f"  {rd.name}: No metrics found")
    
    if len(runs) < 2:
        print("Error: Need at least 2 runs with metrics to compare.")
        sys.exit(1)
    
    # Determine output path
    output_path = args.output
    if not output_path:
        # Use the first run's NPC key to find comparison path
        npc_key = None
        for rd in run_dirs:
            # Path format: outputs/{npc_key}/runs/{run_id}/
            if len(rd.parts) >= 3 and rd.parts[-2] == "runs":
                npc_key = rd.parts[-3]
                break
        if npc_key:
            baseline_label = runs[0].get("run_id", "baseline")
            output_path = str(paths.eval_comparison_path(npc_key, baseline_label))
    
    generate_comparison_report(runs, output_path)


if __name__ == "__main__":
    main()
