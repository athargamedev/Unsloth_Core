#!/usr/bin/env python3
"""
feedback_loop.py — Self-Improving Feedback Loop

Ingests structured evaluation results from evaluate.py's --feedback-json output,
identifies weak concepts (low win rate, poor quality, constraint violations),
and automatically triggers targeted dataset regeneration via generate_dataset.py
to address those weaknesses.

Usage:
    # After evaluation, run the feedback loop:
    python scripts/feedback_loop.py eval/results/feedback/chemistry_instructor_20260515.json

    # With custom thresholds:
    python scripts/feedback_loop.py eval/results/feedback/biology_tutor.json \
        --win-rate-threshold 0.4 --quality-threshold 25 \
        --extra-examples 16 --dry-run

    # Full auto mode with retrain:
    python scripts/feedback_loop.py eval/results/feedback/npc.json \
        --auto --auto-retrain --train-preset fast-3b \
        --baseline exports/npc/baseline.gguf

    # Machine-readable output for CI:
    python scripts/feedback_loop.py eval/results/feedback/npc.json --json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Default thresholds ──────────────────────────────────────────────────────

DEFAULT_WIN_RATE_THRESHOLD = 0.5
DEFAULT_QUALITY_THRESHOLD = 25.0
DEFAULT_VIOLATION_THRESHOLD = 1
DEFAULT_EXTRA_EXAMPLES = 8
DEFAULT_TRAIN_PRESET = "fast-3b"


# ── Helpers ─────────────────────────────────────────────────────────────────

class Tee:
    """Capture printed output while also printing it, for --json mode."""
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)
        sys.__stdout__.write(text)

    def flush(self):
        sys.__stdout__.flush()

    def get_text(self):
        return "".join(self.lines)


def run_cmd(cmd, cwd=None, timeout=600, capture=True):
    """Run a subprocess and return (ok, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd or PROJECT_ROOT),
            capture_output=True, text=True, timeout=timeout,
        )
        ok = result.returncode == 0
        return ok, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Timed out after {timeout}s"
    except FileNotFoundError:
        return False, "", f"Command not found: {cmd[0]}"


# ── Analysis ────────────────────────────────────────────────────────────────

def load_feedback_json(path):
    with open(path) as f:
        return json.load(f)


def identify_weak_concepts(feedback_data, win_rate_threshold, quality_threshold,
                           violation_threshold):
    weak = []
    per_concept = feedback_data.get("per_concept", {})

    for concept, data in per_concept.items():
        reasons = []
        win_rate = data.get("win_rate", 1.0)
        if win_rate < win_rate_threshold:
            reasons.append(f"win_rate={win_rate:.0%}")
        avg_quality = data.get("avg_candidate_quality", 0)
        if avg_quality > quality_threshold:
            reasons.append(f"avg_quality={avg_quality:.1f}")
        violations = data.get("constraint_violations", 0)
        if violations > violation_threshold:
            reasons.append(f"violations={violations}")
        if reasons:
            weak.append({
                "concept": concept,
                "reasons": reasons,
                "data": data,
                "action": {
                    "category": concept.split("/")[0] if "/" in concept else "teaching",
                    "concept_focus": concept.split("/")[1] if "/" in concept else concept,
                    "extra_examples": DEFAULT_EXTRA_EXAMPLES,
                }
            })

    for gap in feedback_data.get("distribution_gaps", []) or []:
        category = gap.get("category")
        shortfall = gap.get("shortfall", 0)
        if not category or shortfall <= 0:
            continue
        weak.append({
            "concept": f"distribution/{category}",
            "reasons": [f"shortfall={shortfall}", f"target={gap.get('target', 0)}", f"actual={gap.get('actual', 0)}"],
            "data": gap,
            "action": {
                "category": category,
                "concept_focus": category,
                "extra_examples": max(DEFAULT_EXTRA_EXAMPLES, int(shortfall)),
            },
        })
    return weak


def print_analysis(feedback_data, weak_concepts):
    print("=" * 60)
    print(f"  FEEDBACK LOOP ANALYSIS")
    print(f"  NPC: {feedback_data.get('npc_key', 'unknown')}")
    print("=" * 60)
    print(f"\nOverall: {feedback_data['candidate_wins']}/{feedback_data['total_examples']} wins "
          f"(win rate: {feedback_data['win_rate']:.0%})")
    print(f"Baseline: {feedback_data.get('baseline', '?')}")
    print(f"Candidate: {feedback_data.get('candidate', '?')}")
    print(f"\nPer-concept breakdown:")
    per_concept = feedback_data.get("per_concept", {})
    for concept, data in sorted(per_concept.items()):
        win_rate = data.get("win_rate", 0)
        quality = data.get("avg_candidate_quality", 0)
        violations = data.get("constraint_violations", 0)
        flag = ""
        if win_rate < DEFAULT_WIN_RATE_THRESHOLD:
            flag = "  ← WEAK"
        elif quality > DEFAULT_QUALITY_THRESHOLD:
            flag = "  ← WEAK"
        elif violations > DEFAULT_VIOLATION_THRESHOLD:
            flag = "  ← WEAK"
        print(f"  {concept:40s} wins={data['candidate_wins']}/{data['total']} "
              f"qual={quality:.0f} viol={violations}{flag}")
    if weak_concepts:
        print(f"\nWeak concepts requiring regeneration ({len(weak_concepts)}):")
        for wc in weak_concepts:
            print(f"  - {wc['concept']}: {', '.join(wc['reasons'])}")
    else:
        print(f"\nNo weak concepts found. Model is performing well across all areas.")







# ── Regeneration ────────────────────────────────────────────────────────────

def generate_targeted_dataset(npc_key, focus_categories, dry_run=False, spec_path=None):
    if not spec_path:
        spec_path = PROJECT_ROOT / "subjects" / f"{npc_key}.json"
    if not Path(spec_path).exists():
        print(f"  [error] Subject spec not found: {spec_path}")
        return False
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "generate_dataset.py"),
        str(spec_path),
        "--technique", "template",
        "--model", "llama3.1:latest",
    ]
    for cat in sorted(focus_categories):
        cmd.extend(["--concept-focus", cat])
    print(f"\n  Target: {spec_path}")
    print(f"  Focus categories: {', '.join(sorted(focus_categories))}")
    if dry_run:
        print(f"  [dry-run] Would execute: {' '.join(cmd)}")
        return True
    print(f"  Running generation with concept focus...")
    ok, stdout, stderr = run_cmd(cmd, timeout=1800)
    if ok:
        print(f"  Done!")
        for line in stdout.strip().split("\n")[-4:]:
            print(f"    {line}")
        return True
    else:
        print(f"  [error] Generation failed (exit code != 0)")
        print(f"  {stderr[:500]}")
        return False


# ── Auto-Retrain ────────────────────────────────────────────────────────────

def run_sanitize(npc_key, technique="template", dry_run=False):
    """Sanitize the regenerated dataset."""
    dataset_path = f"subjects/datasets/{npc_key}/{technique}/train.jsonl"
    clean_path = f"subjects/datasets/{npc_key}/{technique}/train_clean.jsonl"
    if dry_run:
        print(f"  [dry-run] Would sanitize: {dataset_path} -> {clean_path}")
        return True
    print(f"  Sanitizing: {dataset_path}")
    ok, stdout, stderr = run_cmd(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "sanitize_dataset.py"),
         dataset_path, "--output", clean_path, "--strict-canonical"],
        timeout=60,
    )
    if ok:
        print(f"  Sanitize done.")
        return True
    else:
        print(f"  [warn] Sanitize non-fatal: {stderr[:200]}")
        # Sanitize is non-fatal — proceed even if it fails
        return True


def run_training(npc_key, preset, technique="template", dry_run=False):
    """Train a new model with the regenerated dataset."""
    spec_path = PROJECT_ROOT / "subjects" / f"{npc_key}.json"
    if not spec_path.exists():
        print(f"  [error] Spec not found for training: {spec_path}")
        return None

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "train.py"),
        str(spec_path),
        "--from-spec",
        "--technique", technique,
        "--preset", preset,
        "--export-gguf",
    ]
    if dry_run:
        print(f"  [dry-run] Would train: {' '.join(cmd)}")
        return None

    print(f"  Training with preset '{preset}'...")
    ok, stdout, stderr = run_cmd(cmd, timeout=3600)
    if not ok:
        print(f"  [error] Training failed: {stderr[:500]}")
        return None

    # Find the newest GGUF
    export_dir = PROJECT_ROOT / "exports" / npc_key
    ggufs = sorted(export_dir.glob("*.gguf"), key=lambda x: x.stat().st_mtime, reverse=True) if export_dir.exists() else []
    if ggufs:
        print(f"  Model exported: {ggufs[0]}")
        return str(ggufs[0])
    print(f"  [warn] No GGUF found in {export_dir}")
    return None


def run_evaluate(npc_key, baseline_gguf, candidate_gguf, feedback_output_dir, dry_run=False):
    """Evaluate the new model against the baseline with structured output."""
    if dry_run:
        print(f"  [dry-run] Would evaluate candidate={candidate_gguf} vs baseline={baseline_gguf}")
        feedback_path = Path(feedback_output_dir) / f"{npc_key}_post_retrain.json"
        return str(feedback_path)

    feedback_dir = Path(feedback_output_dir)
    feedback_dir.mkdir(parents=True, exist_ok=True)
    feedback_path = feedback_dir / f"{npc_key}_post_retrain.json"
    spec_path = PROJECT_ROOT / "subjects" / f"{npc_key}.json"

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "evaluate.py"),
        "--baseline", str(baseline_gguf),
        "--candidate", str(candidate_gguf),
        "--spec", str(spec_path),
        "--feedback-json", str(feedback_path),
        "--num-questions", "10",
    ]
    print(f"  Evaluating against baseline...")
    ok, stdout, stderr = run_cmd(cmd, timeout=600)
    if ok:
        # Print the last few lines of eval output (win rate summary)
        for line in stdout.strip().split("\n")[-5:]:
            if "win" in line.lower() or "wins" in line.lower() or "rate" in line.lower() or "Summary" in line:
                print(f"    {line.strip()}")
        print(f"  Eval results: {feedback_path}")
        return str(feedback_path)
    else:
        print(f"  [warn] Evaluation had issues: {stderr[:300]}")
        # Non-fatal — return the path anyway if it was created
        if feedback_path.exists():
            return str(feedback_path)
        return None


# ── Pipeline State ──────────────────────────────────────────────────────────

PIPELINE_STATE_PATH = PROJECT_ROOT / "eval" / "results" / "pipeline_state.json"


def update_pipeline_state(npc_key, state_update):
    """Update the shared pipeline state file, merging with any existing state."""
    state = {}
    if PIPELINE_STATE_PATH.exists():
        try:
            with open(PIPELINE_STATE_PATH) as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            state = {}
    state[npc_key] = {
        **state.get(npc_key, {}),
        **state_update,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    PIPELINE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PIPELINE_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\n  Pipeline state updated: {PIPELINE_STATE_PATH}")


# ── Main Loop ───────────────────────────────────────────────────────────────

def run_feedback_loop(feedback_path, win_rate_threshold=DEFAULT_WIN_RATE_THRESHOLD,
                      quality_threshold=DEFAULT_QUALITY_THRESHOLD,
                      violation_threshold=DEFAULT_VIOLATION_THRESHOLD,
                      dry_run=False, auto_yes=False, skip_gap_detection=False,
                      save_gaps=None, json_output=False,
                      auto_retrain=False, train_preset=DEFAULT_TRAIN_PRESET,
                      baseline_gguf=None):
    """Full feedback loop: analyze → regenerate → optionally retrain."""
    # Capture human-readable output for --json mode
    tee = Tee() if json_output else None

    # ── 1. Load ────────────────────────────────────────────────────────
    feedback_data = load_feedback_json(feedback_path)
    npc_key = feedback_data.get("npc_key", "unknown")
    candidate_model = feedback_data.get("candidate", "")

    # ── 2. Analyze ─────────────────────────────────────────────────────
    weak_concepts = identify_weak_concepts(
        feedback_data, win_rate_threshold, quality_threshold, violation_threshold
    )
    print_analysis(feedback_data, weak_concepts)

    # Build the result dict
    result = {
        "status": "ok",
        "npc_key": npc_key,
        "weak_concepts": [],
        "gap_results": [],
        "regeneration": {"ok": False, "focus_categories": []},
        "auto_retrain": None,
        "pipeline_state": None,
    }

    if not weak_concepts:
        print("\nNothing to improve. Model is performing well across all areas.")
        result["status"] = "no_weak_concepts"
        update_pipeline_state(npc_key, {
            "status": "healthy",
            "weak_concepts_count": 0,
            "last_feedback": datetime.now(timezone.utc).isoformat(),
        })
        if json_output:
            print(json.dumps(result, indent=2))
        return 0

    result["weak_concepts"] = [
        {"concept": wc["concept"], "reasons": wc["reasons"]}
        for wc in weak_concepts
    ]

    # ── 3. Knowledge gap detection ─────────────────────────────────────
    gap_results = []
    if not skip_gap_detection:
        print(f"\n{'─' * 40}")
        print("  Checking knowledge coverage for weak concepts...")
        print("  (gap detection requires external service — skipping)")
        result["gap_results"] = gap_results

        if save_gaps:
            save_path = Path(save_gaps)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w") as f:
                json.dump(gap_results, f, indent=2)
            print(f"\n  Gap report saved to: {save_path}")
    else:
        print("\n  (gap detection skipped)")

    # ── 4. Plan regeneration ───────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  REGENERATION PLAN")
    print(f"{'=' * 60}")
    focus_categories = sorted(set(wc["action"]["category"] for wc in weak_concepts))
    for wc in weak_concepts:
        print(f"  {wc['concept']}: {', '.join(wc['reasons'])}")
    print(f"\n  Unique categories to boost: {', '.join(focus_categories)}")
    if auto_retrain:
        print(f"  Auto-retrain enabled: preset={train_preset}, baseline={baseline_gguf}")

    # ── 5. Confirm ─────────────────────────────────────────────────────
    if not auto_yes and not dry_run:
        print(f"\nProceed with targeted regeneration? [Y/n] ", end="", flush=True)
        try:
            response = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            response = "n"
        if response not in ("", "y", "yes"):
            print("Cancelled.")
            result["status"] = "cancelled"
            if json_output:
                print(json.dumps(result, indent=2))
            return 1

    # ── 6. Execute regeneration ────────────────────────────────────────
    print(f"\n{'─' * 40}")
    ok = generate_targeted_dataset(npc_key, focus_categories, dry_run=dry_run)
    result["regeneration"] = {"ok": ok, "focus_categories": focus_categories}

    if not ok:
        print(f"\n  Regeneration failed.")
        result["status"] = "regeneration_failed"
        if json_output:
            print(json.dumps(result, indent=2))
        update_pipeline_state(npc_key, {
            "status": "regeneration_failed",
            "weak_concepts_count": len(weak_concepts),
            "last_feedback": datetime.now(timezone.utc).isoformat(),
        })
        return 1

    # ── 7. Auto-retrain ────────────────────────────────────────────────
    trained_gguf = None
    if auto_retrain and not dry_run:
        print(f"\n{'─' * 40}")
        print("  AUTO-RETRAIN PHASE")
        print(f"{'─' * 40}")

        # Sanitize
        print(f"\n  Step 1: Sanitize dataset...")
        run_sanitize(npc_key, dry_run=dry_run)

        # Train
        print(f"\n  Step 2: Train new model...")
        trained_gguf = run_training(npc_key, train_preset, dry_run=dry_run)
        result["auto_retrain"] = {"trained_gguf": trained_gguf}

        if trained_gguf and baseline_gguf:
            # Evaluate
            print(f"\n  Step 3: Evaluate against baseline...")
            eval_feedback_path = run_evaluate(npc_key, baseline_gguf, trained_gguf,
                                               PROJECT_ROOT / "eval" / "results" / "feedback",
                                               dry_run=dry_run)
            result["auto_retrain"]["eval_feedback_path"] = eval_feedback_path

            if eval_feedback_path and Path(eval_feedback_path).exists():
                # Load eval results for pipeline state
                try:
                    post_eval = load_feedback_json(eval_feedback_path)
                    result["auto_retrain"]["win_rate"] = post_eval.get("win_rate")
                    result["auto_retrain"]["candidate_wins"] = post_eval.get("candidate_wins")
                    result["auto_retrain"]["total_examples"] = post_eval.get("total_examples")
                except Exception:
                    pass
        elif trained_gguf:
            print(f"  (skipping eval: no --baseline provided)")
    elif auto_retrain and dry_run:
        print(f"\n  [dry-run] Would auto-retrain with preset '{train_preset}'")
        result["auto_retrain"] = {
            "trained_gguf": None,
            "eval_feedback_path": None,
            "dry_run": True,
            "train_preset": train_preset,
            "baseline": str(baseline_gguf) if baseline_gguf else None,
        }

    # ── 8. Update pipeline state ───────────────────────────────────────
    state_update = {
        "status": "regenerated",
        "weak_concepts_count": len(weak_concepts),
        "focus_categories": focus_categories,
        "last_feedback": datetime.now(timezone.utc).isoformat(),
        "auto_retrain_complete": auto_retrain and trained_gguf is not None,
    }
    if trained_gguf:
        state_update["latest_gguf"] = trained_gguf
    if result.get("auto_retrain") and result["auto_retrain"].get("win_rate") is not None:
        state_update["latest_win_rate"] = result["auto_retrain"]["win_rate"]
    update_pipeline_state(npc_key, state_update)
    result["pipeline_state"] = state_update

    # ── 9. Summary ─────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  FEEDBACK LOOP COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Regenerated dataset with focus on: {', '.join(focus_categories)}")
    if auto_retrain and trained_gguf:
        print(f"  Retrained model: {trained_gguf}")
    if dry_run:
        print(f"  (dry-run mode — no changes made)")
    if not auto_retrain and not dry_run:
        print(f"\n  Next step: train and re-evaluate:")
        print(f"    ./ucore train subjects/NPC_specs/{npc_key}.json --preset {train_preset}")
        print(f"    ./ucore evaluate --baseline <old.gguf> --candidate <new.gguf>"
              f" --spec subjects/NPC_specs/{npc_key}.json --feedback-json eval/results/feedback/{npc_key}_round2.json")
    print(f"  Pipeline state: {PIPELINE_STATE_PATH}")

    if json_output:
        print(json.dumps(result, indent=2))

    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Self-Improving Feedback Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("feedback_json", help="Path to feedback JSON from evaluate.py --feedback-json")

    # Thresholds
    parser.add_argument("--win-rate-threshold", type=float, default=DEFAULT_WIN_RATE_THRESHOLD)
    parser.add_argument("--quality-threshold", type=float, default=DEFAULT_QUALITY_THRESHOLD)
    parser.add_argument("--violation-threshold", type=int, default=DEFAULT_VIOLATION_THRESHOLD)

    # Behavior
    parser.add_argument("--dry-run", action="store_true", help="Analyze and plan without executing")
    parser.add_argument("--auto", "-y", action="store_true", help="Auto-accept all suggestions")
    parser.add_argument("--skip-gap-detection", action="store_true", help="Skip knowledge coverage check")
    parser.add_argument("--save-gaps", help="Save gap analysis to JSON file")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON summary")

    # Auto-retrain
    parser.add_argument("--auto-retrain", action="store_true",
                        help="After regeneration, auto-retrain and re-evaluate")
    parser.add_argument("--train-preset", default=DEFAULT_TRAIN_PRESET,
                        help=f"Training preset (default: {DEFAULT_TRAIN_PRESET})")
    parser.add_argument("--baseline", help="Baseline GGUF path for auto-evaluation after retrain")

    args = parser.parse_args()

    if not os.path.exists(args.feedback_json):
        print(f"Error: Feedback JSON not found: {args.feedback_json}")
        print("\nRun evaluate.py with --feedback-json to generate it first:")
        print(f"  python scripts/evaluate.py ... --feedback-json {args.feedback_json}")
        sys.exit(1)

    if args.auto_retrain and not args.baseline and not args.dry_run:
        print("Warning: --auto-retrain without --baseline will train but skip evaluation.")

    sys.exit(run_feedback_loop(
        args.feedback_json,
        win_rate_threshold=args.win_rate_threshold,
        quality_threshold=args.quality_threshold,
        violation_threshold=args.violation_threshold,
        dry_run=args.dry_run,
        auto_yes=args.auto,
        skip_gap_detection=args.skip_gap_detection,
        save_gaps=args.save_gaps,
        json_output=args.json,
        auto_retrain=args.auto_retrain,
        train_preset=args.train_preset,
        baseline_gguf=args.baseline,
    ))


if __name__ == "__main__":
    main()
