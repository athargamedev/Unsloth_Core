#!/usr/bin/env python3
"""
feedback_loop.py — Self-Improving Feedback Loop (REFACTORED)

Orchestrates a working feedback loop using the actively-maintained CLI pipeline:

  1. Read evaluate.py's feedback JSON → identify weak concepts
  2. Run generate-ollama --concept-focus to regenerate only failing categories
  3. Run sanitize to clean the regenerated dataset
  4. Run dataset-eval to gate the result
  5. Optionally retrain and re-evaluate

This replaces the previous non-functional 1305-line implementation.
The canonical repair path is: dataset-eval → generate-ollama --concept-focus → sanitize → dataset-eval

Usage:
    # Dry-run: show what would be regenerated
    python scripts/training/feedback_loop.py eval/results/feedback/npc.json --dry-run

    # Full auto mode with retrain
    python scripts/training/feedback_loop.py eval/results/feedback/npc.json \\
        --auto --auto-retrain --train-preset fast-3b --baseline exports/npc/baseline.gguf

    # Machine-readable output
    python scripts/training/feedback_loop.py eval/results/feedback/npc.json --json
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import paths
from src.core.ops.npc_production_strategy import classify_feedback_cycle, density_repair_needed

DEFAULT_TRAIN_PRESET = "fast-3b"
DEFAULT_CONCEPT_FOCUS_CATEGORIES = ["identity", "refusal", "dialogue"]
DEFAULT_EXTRA_EXAMPLES = 4


def _ucore(args_list: list[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    """Run a ucore CLI command."""
    cmd = [sys.executable, str(PROJECT_ROOT / "src" / "cli" / "ucore")] + args_list
    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    print(f"[RUN] {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def load_feedback(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def identify_weak_concepts(
    feedback_data,
    win_rate_threshold=0.5,
    quality_threshold=25.0,
    violation_threshold=1,
    extra_examples=DEFAULT_EXTRA_EXAMPLES,
):
    """Identify weak concepts from structured feedback data (per_concept format).

    Legacy API — preserved for backward compatibility.
    The newer extract_weak_categories() reads evaluate.py's full feedback JSON format.
    """
    weak = []
    per_concept = feedback_data.get("per_concept", {})

    for concept, data in per_concept.items():
        reasons = []
        win_rate = data.get("win_rate", 1.0)
        if win_rate < win_rate_threshold:
            reasons.append(f"win_rate={win_rate:.0%}")
        avg_quality = data.get("avg_candidate_quality", 0)
        if avg_quality < quality_threshold:
            reasons.append(f"avg_quality={avg_quality:.1f}")
        violations = data.get("constraint_violations", 0)
        if violations > violation_threshold:
            reasons.append(f"violations={violations}")
        if reasons:
            weak.append(
                {
                    "concept": concept,
                    "reasons": reasons,
                    "data": data,
                    "action": {
                        "category": concept.split("/")[0] if "/" in concept else "teaching",
                        "concept_focus": concept.split("/")[1] if "/" in concept else concept,
                        "extra_examples": extra_examples,
                    },
                }
            )
    return weak


class LocalGapDetector:
    """Analyze knowledge/training-density gaps for weak concepts.

    Loads NPC spec, primer, and training data to classify each weak concept
    as a knowledge_gap (missing from primer), training_density_gap (< 8 examples),
    or model_capacity_gap (primer + density adequate but model still fails).
    """

    def __init__(self, npc_key: str, technique: str = "template"):
        self.npc_key = npc_key
        self.technique = technique
        self.spec_path = None
        self.primer_path = None
        self.train_clean_path = None
        self.spec_concepts = []
        self.primer_text = ""
        self._resolve_and_load()

    def _resolve_and_load(self):
        try:
            self.spec_path = paths.spec_path(self.npc_key)
        except Exception:
            self.spec_path = PROJECT_ROOT / "data" / "npcs" / "specs" / f"{self.npc_key}.json"

        self.primer_path = (
            PROJECT_ROOT / "data" / "npcs" / "reference_docs" / f"{self.npc_key}_primer.md"
        )

        try:
            self.train_clean_path = paths.dataset_dir(self.npc_key) / self.technique / "train_clean.jsonl"
        except Exception:
            self.train_clean_path = (
                PROJECT_ROOT / "data" / "datasets" / self.npc_key / self.technique / "train_clean.jsonl"
            )

        if self.spec_path and self.spec_path.exists():
            try:
                with open(self.spec_path, encoding="utf-8") as f:
                    spec_data = json.load(f)
                    self.spec_concepts = spec_data.get("concepts", [])
            except Exception as e:
                print(f"  [LocalGapDetector] Warning: failed to load spec JSON: {e}")
        else:
            print(f"  [LocalGapDetector] Warning: spec path not found: {self.spec_path}")

        if self.primer_path and self.primer_path.exists():
            try:
                with open(self.primer_path, encoding="utf-8") as f:
                    self.primer_text = f.read()
            except Exception as e:
                print(f"  [LocalGapDetector] Warning: failed to load primer markdown: {e}")
        else:
            print(f"  [LocalGapDetector] Warning: primer path not found: {self.primer_path}")

    def count_primer_occurrences(self, concept_name: str, aliases: list) -> int:
        if not self.primer_text:
            return 0
        text_lower = self.primer_text.lower()
        count = text_lower.count(concept_name.lower().strip())
        for alias in aliases:
            count += text_lower.count(alias.lower().strip())
        return count

    def count_training_examples(self, concept_name: str) -> int:
        if not self.train_clean_path or not self.train_clean_path.exists():
            return 0
        count = 0
        target_concept = concept_name.lower().strip()
        try:
            with open(self.train_clean_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        meta = data.get("metadata", {})
                        ex_concept = meta.get("concept")
                        if ex_concept and ex_concept.lower().strip() == target_concept:
                            count += 1
                    except Exception:
                        continue
        except Exception as e:
            print(f"  [LocalGapDetector] Warning: failed to read cleaned training file: {e}")
        return count

    def detect_gaps(self, weak_concepts: list) -> list:
        gap_results = []
        for wc in weak_concepts:
            concept_key = wc.get("concept", "unknown")
            reasons = wc.get("reasons", [])

            category = None
            concept_name = concept_key
            if "/" in concept_key:
                category, concept_name = concept_key.split("/", 1)

            spec_c = None
            concept_name_lower = concept_name.lower().strip()
            category_lower = category.lower().strip() if category else None

            for c in self.spec_concepts:
                name = c.get("name", "")
                c_category = c.get("category", "")
                if name.lower().strip() == concept_name_lower:
                    if category_lower is None or c_category.lower().strip() == category_lower:
                        spec_c = c
                        break
            if not spec_c:
                for c in self.spec_concepts:
                    name = c.get("name", "")
                    if name.lower().strip() == concept_name_lower:
                        spec_c = c
                        break

            aliases = []
            if spec_c:
                aliases = spec_c.get("aliases", [])
                concept_name = spec_c.get("name", concept_name)

            primer_occurrences = self.count_primer_occurrences(concept_name, aliases)
            training_examples_count = self.count_training_examples(concept_name)

            if primer_occurrences == 0:
                gap_type = "knowledge_gap"
                rec = "Source document lacks coverage. Add descriptive sections to primer."
            elif training_examples_count < 8:
                gap_type = "training_density_gap"
                rec = "Low example density. Trigger synthetic generation for concept with focus."
            else:
                gap_type = "model_capacity_gap"
                rec = "The model failed to acquire the concept; upgrade training preset, increase epochs, or check format."

            gap_results.append({
                "concept": concept_key,
                "gap_type": gap_type,
                "primer_occurrences": primer_occurrences,
                "training_examples_count": training_examples_count,
                "action_recommendation": rec,
                "reasons": reasons,
            })
        return gap_results


def extract_weak_categories(feedback: dict) -> list[str]:
    """Extract failing categories from feedback JSON (evaluate.py output)."""
    weak = []

    # From individual example scores
    for example in feedback.get("examples", []):
        cat = example.get("category")
        win = example.get("win", None)
        quality = example.get("candidate_quality", 100)
        if cat and (win is False or (isinstance(quality, (int, float)) and quality < 30)):
            if cat not in weak:
                weak.append(cat)

    # From overall scores
    for cat_key in ["identity", "teaching", "dialogue", "quest", "refusal"]:
        cat_data = feedback.get(cat_key, {})
        if isinstance(cat_data, dict):
            win_rate = cat_data.get("win_rate", 1.0)
            if isinstance(win_rate, (int, float)) and win_rate < 0.5 and cat_key not in weak:
                weak.append(cat_key)

    # From aggregated summary
    agg = feedback.get("aggregated_summary", {})
    for cat, cat_info in agg.items():
        if isinstance(cat_info, dict):
            wr = cat_info.get("win_rate", 1.0)
            if isinstance(wr, (int, float)) and wr < 0.5 and cat not in weak:
                weak.append(cat)

    return weak or DEFAULT_CONCEPT_FOCUS_CATEGORIES[:]


def run_feedback_loop(
    feedback_json: str,
    *,
    dry_run: bool = False,
    auto: bool = False,
    auto_retrain: bool = False,
    train_preset: str = DEFAULT_TRAIN_PRESET,
    baseline: str | None = None,
    concept_focus: list[str] | None = None,
    strategy_profile: str = "npc-production-grounded",
    json_output: bool = False,
) -> dict:
    feedback = load_feedback(feedback_json)
    feedback_path = Path(feedback_json)
    npc_key = feedback.get("npc_key", feedback_path.stem)

    # Extract weak categories if not explicitly provided
    weak_categories = concept_focus or extract_weak_categories(feedback)

    # Strategy classification
    strategy_result = classify_feedback_cycle(feedback, profile=strategy_profile)
    density_result = density_repair_needed(feedback)

    result = {
        "npc_key": npc_key,
        "feedback_source": feedback_json,
        "weak_categories": weak_categories,
        "strategy_decision": strategy_result,
        "density_decision": density_result,
        "actions_taken": [],
        "status": "analysis_complete",
    }

    if not json_output:
        print(f"\n=== Feedback Loop: {npc_key} ===")
        print(f"  Weak categories: {weak_categories}")
        print(f"  Strategy: {strategy_result}")
        print(f"  Density: {density_result}")

        if density_result.get("needed"):
            print(f"  ⚠  Density repair needed: candidate avg {density_result.get('candidate_words')} words "
                  f"(target min {density_result.get('target_min_words')})")

    if dry_run:
        result["status"] = "dry_run"
        if not json_output:
            print(f"\n  [DRY-RUN] Would regenerate categories: {weak_categories}")
            if auto_retrain:
                print(f"  [DRY-RUN] Would retrain with preset: {train_preset}")
        return result

    if not auto:
        if not json_output:
            print("\n  Use --auto to execute. Dry run complete.")
        result["status"] = "dry_run"
        return result

    # Step 1: Regenerate weak categories
    spec_path = paths.spec_path(npc_key)
    if not spec_path.exists():
        if not json_output:
            print(f"  ERROR: Spec not found at {spec_path}")
        result["status"] = "error"
        result["error"] = f"Spec not found: {spec_path}"
        return result

    # Generate-ollama with concept focus
    gen_args = ["generate-ollama", str(spec_path), "--fresh"]
    for cat in weak_categories:
        gen_args.extend(["--concept-focus", cat])

    if not json_output:
        print(f"\n  [1/4] Regenerating {weak_categories}...")
    gen_r = _ucore(gen_args)
    result.setdefault("steps", []).append({
        "step": "generate",
        "command": "generate-ollama",
        "exit_code": gen_r.returncode,
        "stdout_snippet": gen_r.stdout[-300:] if gen_r.stdout else "",
        "stderr_snippet": gen_r.stderr[-300:] if gen_r.stderr else "",
    })
    if gen_r.returncode != 0:
        if not json_output:
            print(f"  ERROR: Generation failed (exit {gen_r.returncode})")
        result["status"] = "error"
        result["error_detail"] = gen_r.stderr[-500:] if gen_r.stderr else ""
        return result
    result["actions_taken"].append("regenerated_weak_categories")

    # Step 2: Sanitize
    technique = "ollama"
    train_path = paths.dataset_train_path(npc_key, technique)
    clean_path = train_path.parent / "train_clean.jsonl"

    if not json_output:
        print(f"  [2/4] Sanitizing {train_path}...")
    san_args = [
        "sanitize", str(train_path),
        "--output", str(clean_path),
        "--strict-canonical", "--require-complete-metadata",
        "--no-dedup",  # Preserve category counts during repair
    ]
    san_r = _ucore(san_args)
    result.setdefault("steps", []).append({
        "step": "sanitize",
        "command": "sanitize",
        "exit_code": san_r.returncode,
    })
    if san_r.returncode != 0:
        if not json_output:
            print(f"  WARNING: Sanitize had issues (exit {san_r.returncode})")
    result["actions_taken"].append("sanitized")

    # Step 3: Dataset-eval quality gate
    if not json_output:
        print(f"  [3/4] Running dataset-eval quality gate...")
    eval_args = [
        "dataset-eval", str(spec_path),
        "--technique", technique,
        "--mode", "fast",
    ]
    eval_r = _ucore(eval_args)
    result.setdefault("steps", []).append({
        "step": "dataset_eval",
        "command": "dataset-eval",
        "exit_code": eval_r.returncode,
    })
    eval_passed = eval_r.returncode == 0
    result["quality_gate_passed"] = eval_passed
    result["actions_taken"].append("quality_gated")

    if not json_output:
        print(f"  Quality gate: {'PASSED' if eval_passed else 'FAILED'}")

    # Step 4: Optional retrain
    if auto_retrain and eval_passed:
        if not json_output:
            print(f"  [4/4] Training with preset={train_preset}...")
        train_args = [
            "train", str(spec_path),
            "--technique", technique,
            "--preset", train_preset,
            "--export-gguf",
        ]
        train_r = _ucore(train_args)
        result.setdefault("steps", []).append({
            "step": "train",
            "command": "train",
            "exit_code": train_r.returncode,
        })
        if train_r.returncode == 0:
            result["actions_taken"].append("retrained")
            result["status"] = "full_cycle_complete"
        else:
            result["status"] = "train_failed"
    elif auto_retrain and not eval_passed:
        if not json_output:
            print(f"  Skipping retrain: quality gate failed.")
        result["status"] = "gate_failed"
    else:
        result["status"] = "regeneration_complete"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Self-Improving Feedback Loop — focuses regeneration on weak categories"
    )
    parser.add_argument("feedback_json", help="Path to feedback JSON from evaluate --feedback-json")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without regenerating")
    parser.add_argument("--auto", "-y", action="store_true", help="Execute the full loop")
    parser.add_argument("--auto-retrain", action="store_true", help="Retrain after regeneration")
    parser.add_argument("--train-preset", default=DEFAULT_TRAIN_PRESET, help="Training preset")
    parser.add_argument("--baseline", help="Baseline GGUF for evaluation")
    parser.add_argument("--concept-focus", nargs="*", help="Categories to focus on (default: auto-detect)")
    parser.add_argument("--strategy-profile", default="npc-production-grounded", help="Strategy profile")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")

    args = parser.parse_args()

    if not Path(args.feedback_json).exists():
        print(f"Error: feedback JSON not found: {args.feedback_json}", file=sys.stderr)
        sys.exit(1)

    result = run_feedback_loop(
        args.feedback_json,
        dry_run=args.dry_run,
        auto=args.auto,
        auto_retrain=args.auto_retrain,
        train_preset=args.train_preset,
        baseline=args.baseline,
        concept_focus=args.concept_focus,
        strategy_profile=args.strategy_profile,
        json_output=args.json,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n=== Result ===")
        print(f"  Status: {result['status']}")
        print(f"  Actions: {result['actions_taken']}")
        print(f"  Quality gate: {result.get('quality_gate_passed', 'N/A')}")
        if result.get("error"):
            print(f"  Error: {result['error']}")

    sys.exit(0 if result.get("status") not in ("error", "gate_failed", "train_failed") else 1)


if __name__ == "__main__":
    main()
