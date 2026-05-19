#!/usr/bin/env python3
"""
compare_runs.py — Compare two training runs by run_id.

Resolves run manifests, finds the exported GGUF, and runs evaluate.py
for a side-by-side comparison. Results go to eval/comparisons/.

Usage:
    python scripts/evaluation/compare_runs.py chemistry_instructor \\
        --baseline-run 20260512_llama-3b-fast_001 \\
        --candidate-run 20260512_llama-3b-quality_001

    # With an LLM judge
    python scripts/evaluation/compare_runs.py chemistry_instructor \\
        --baseline-run 20260512_fast_001 \\
        --candidate-run 20260512_quality_001 \\
        --judge
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from scripts._repo_root import PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))
from _config import paths


def find_gguf_for_run(npc_key: str, run_id: str) -> tuple[str, str]:
    """Find the best matching GGUF for a given run.

    Returns (gguf_path, model_id). Exits on failure.
    """
    run_dir = paths.run_dir(npc_key, run_id)
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        print(f"       Available runs for {npc_key}:")
        runs_dir = paths.output_dir(npc_key) / "runs"
        if runs_dir.exists():
            for d in sorted(runs_dir.iterdir()):
                if d.is_dir():
                    print(f"         {d.name}")
        sys.exit(1)

    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        print(f"Error: No run_manifest.json in {run_dir}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    model_id = manifest.get("model_id", "unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
    model_short = None
    technique = manifest.get("dataset", {}).get("technique", "template")
    try:
        model_short = paths.model_short_name(model_id)
    except Exception:
        pass

    # Look for GGUF in exports/{npc_key}/
    export_dir = paths.export_dir(npc_key)
    if not export_dir.exists():
        print(f"Error: No exports directory for {npc_key}")
        print(f"       Export first: ./ucore export {npc_key}")
        sys.exit(1)

    # Search for matching GGUF
    ggufs = []
    if model_short:
        # Try specific model naming first
        ggufs = sorted(export_dir.glob(f"{npc_key}-{model_short}-*.gguf"))
    if not ggufs:
        # Fall back to any GGUF for this NPC
        ggufs = sorted(export_dir.glob(f"{npc_key}-*.gguf"))
    if not ggufs:
        # Last resort: any GGUF in the export dir
        ggufs = sorted(export_dir.glob("*.gguf"))

    if not ggufs:
        print(f"Error: No GGUF found for {npc_key} in {export_dir}")
        print(f"       Export first: ./ucore export {npc_key}")
        sys.exit(1)

    return str(ggufs[0]), model_id


def main():
    parser = argparse.ArgumentParser(
        description="Compare two training runs by run_id"
    )
    parser.add_argument("npc_key", help="NPC key (e.g., chemistry_instructor)")
    parser.add_argument("--baseline-run", required=True, help="Baseline run ID")
    parser.add_argument("--candidate-run", required=True, help="Candidate run ID")
    parser.add_argument("--spec", help="Subject spec path (auto-detected if omitted)")
    parser.add_argument("--num-questions", type=int, default=10,
                        help="Number of eval questions (default: 10)")
    parser.add_argument("--judge", action="store_true",
                        help="Use local Ollama judge")
    parser.add_argument("--output", "-o", help="Output report path")
    args = parser.parse_args()

    # Resolve GGUF paths
    baseline_gguf, model_id = find_gguf_for_run(args.npc_key, args.baseline_run)
    candidate_gguf, _ = find_gguf_for_run(args.npc_key, args.candidate_run)

    # Auto-detect spec
    spec_path = args.spec
    if not spec_path:
        spec_guess = paths.subjects_root() / f"{args.npc_key}.json"
        if spec_guess.exists():
            spec_path = str(spec_guess)
            print(f"Auto-detected spec: {spec_path}")

    # Build evaluate.py command
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "evaluate.py"),
        "--baseline", baseline_gguf,
        "--candidate", candidate_gguf,
    ]
    if spec_path:
        cmd.extend(["--spec", spec_path])
    cmd.extend(["--num-questions", str(args.num_questions)])
    if args.judge:
        cmd.append("--judge")

    # Default output path
    if not args.output:
        report_dir = paths.eval_comparison_dir()
        report_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        args.output = str(
            report_dir
            / f"{args.npc_key}_{args.baseline_run}_vs_{args.candidate_run}_{today}.md"
        )
    cmd.extend(["--output", args.output])

    # Track results
    cmd.append("--track")

    print(f"{'=' * 60}")
    print(f"  RUN COMPARISON")
    print(f"  NPC:        {args.npc_key}")
    print(f"  Baseline:   {args.baseline_run}")
    print(f"  Candidate:  {args.candidate_run}")
    print(f"{'=' * 60}")
    print(f"  Baseline GGUF:  {baseline_gguf}")
    print(f"  Candidate GGUF: {candidate_gguf}")
    print(f"  Output:         {args.output}")
    print()

    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
    print(f"\n{'=' * 60}")
    print(f"  Comparison complete: {args.output}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
