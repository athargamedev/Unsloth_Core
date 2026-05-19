#!/usr/bin/env python3
"""One-shot feedback improvement cycle for a single NPC.

Usage:
    python3 scripts/training/iterate_feedback.py chemistry_instructor --preset fast-3b

Runs: evaluate → feedback (auto) → train → evaluate → report
All on the active subject. Assumes the dataset already exists.
"""

from __future__ import annotations
import sys, os, argparse, json, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV = REPO / "unsloth_env" / "bin" / "python"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("npc_key", help="NPC key (e.g. chemistry_instructor)")
    parser.add_argument("--preset", default="fast-3b", help="Training preset")
    args = parser.parse_args()

    npc = args.npc_key
    spec = REPO / "subjects" / f"{npc}.json"
    if not spec.exists():
        print(f"Subject spec not found: {spec}")
        sys.exit(1)

    feedback_json = REPO / "eval" / "results" / "feedback" / f"{npc}.json"
    feedback_json.parent.mkdir(parents=True, exist_ok=True)

    steps = [
        (f"Evaluate {npc}",
         f"{VENV} scripts/evaluation/evaluate.py "
         f"--spec {spec} --feedback-json {feedback_json}"),
        (f"Feedback loop for {npc}",
         f"{VENV} scripts/training/feedback_loop.py {feedback_json} --auto"),
        (f"Train {npc}",
         f"{VENV} scripts/training/train.py {spec} --preset {args.preset} --export-gguf"),
        (f"Re-evaluate {npc}",
         f"{VENV} scripts/evaluation/evaluate.py "
         f"--spec {spec} --feedback-json {feedback_json}"),
    ]

    for label, cmd in steps:
        print(f"\n{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        ret = subprocess.run(cmd, shell=True, cwd=REPO)
        if ret.returncode != 0:
            print(f"[FAIL] {label} exited with code {ret.returncode}")
            sys.exit(1)

    print(f"\n✓ {npc} improvement cycle complete")

if __name__ == "__main__":
    main()
