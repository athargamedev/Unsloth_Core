# Phase 5 — Evaluation & Comparison Framework Implementation Plan

> **Goal:** Standardize evaluation workflows, add CLI access to all eval tools, enable run-vs-run comparison by run_id, add automated promotion rules, and wire results tracking into the pipeline.

**Architecture:** All eval flags converge on existing scripts (`evaluate.py`, `quick_eval.py`, `track_eval_results.py`) through `ucore`. A new `compare` script pairs runs by their manifests. Promotion rules gate the `best` symlink.

**State after Phase 4:**
- Exists: `scripts/evaluate.py` (full comparison), `scripts/quick_eval.py`, `scripts/track_eval_results.py`
- Exists: `docs/EVALUATION_WORKFLOW.md`, eval path helpers in `_config/paths.py`
- Missing: ucore subcommands, compare-by-run_id, eval presets, promotion gates

---

### Task 1: Add `ucore evaluate` subcommand

**Objective:** `./ucore evaluate --baseline <gguf> --candidate <gguf> --spec <spec>` calls evaluate.py.

**Files:**
- Modify: `ucore` (add subparser + handler)

**Step 1: Add subparser**

Key flags from `evaluate.py`:
- `--baseline`, `--candidate`, `--model` (for single-model modes)
- `--spec`, `--val-data`, `--num-questions`
- `--judge`, `--judge-model`
- `--output`, `--report-html`
- `--track`, `--interactive`
- `--port`, `--host`

```python
eval_p = subparsers.add_parser("evaluate", help="Compare two GGUF models side-by-side")
eval_p.add_argument("--baseline", help="Baseline GGUF model path")
eval_p.add_argument("--candidate", help="Candidate GGUF model path")
eval_p.add_argument("--model", "-m", help="Single model GGUF path (for interactive)")
eval_p.add_argument("--spec", "-s", help="Subject spec JSON")
eval_p.add_argument("--val-data", help="Validation JSONL path")
eval_p.add_argument("--num-questions", type=int, default=10, help="Number of eval questions")
eval_p.add_argument("--output", "-o", help="Output report path")
eval_p.add_argument("--report-html", action="store_true", help="Generate HTML report")
eval_p.add_argument("--judge", action="store_true", help="Use local Ollama judge")
eval_p.add_argument("--judge-model", default="llama3.1:latest", help="Judge model")
eval_p.add_argument("--track", action="store_true", help="Track results in eval/results/")
eval_p.add_argument("--interactive", "-i", action="store_true", help="Interactive chat mode")
eval_p.add_argument("--port", type=int, default=8888, help="llama-server port")
```

**Step 2: Add handler**

```python
elif args.command == "evaluate":
    cmd = [PYTHON, str(SCRIPTS_DIR / "evaluate.py")]
    if args.baseline: cmd.extend(["--baseline", args.baseline])
    if args.candidate: cmd.extend(["--candidate", args.candidate])
    if args.model: cmd.extend(["--model", args.model])
    if args.spec: cmd.extend(["--spec", args.spec])
    if args.val_data: cmd.extend(["--val-data", args.val_data])
    if args.num_questions: cmd.extend(["--num-questions", str(args.num_questions)])
    if args.output: cmd.extend(["--output", args.output])
    if args.report_html: cmd.append("--report-html")
    if args.judge: cmd.append("--judge")
    if args.judge_model: cmd.extend(["--judge-model", args.judge_model])
    if args.track: cmd.append("--track")
    if args.interactive: cmd.append("--interactive")
    if args.port: cmd.extend(["--port", str(args.port)])
    run_cmd(cmd)
```

---

### Task 2: Add `ucore quick-eval` subcommand

**Objective:** `./ucore quick-eval <adapter_or_gguf> [--samples 50]` calls quick_eval.py.

**Files:**
- Modify: `ucore`

```python
qe_p = subparsers.add_parser("quick-eval", help="Quick local evaluation (llama-cpp-python)")
qe_p.add_argument("adapter_path", help="Path to LoRA adapter or merged GGUF")
qe_p.add_argument("--samples", "-n", type=int, default=20, help="Number of validation samples")
qe_p.add_argument("--spec", "-s", help="Subject spec JSON")
qe_p.add_argument("--val-data", help="Validation JSONL (auto-detected if omitted)")
```

Handler:

```python
elif args.command == "quick-eval":
    cmd = [PYTHON, str(SCRIPTS_DIR / "quick_eval.py"), args.adapter_path]
    if args.samples: cmd.extend(["--samples", str(args.samples)])
    if args.spec: cmd.extend(["--spec", args.spec])
    if args.val_data: cmd.extend(["--val-data", args.val_data])
    run_cmd(cmd)
```

---

### Task 3: Add `ucore track` subcommand

**Objective:** `./ucore track --npc-key <key> --win-rate 0.75` and `./ucore track --show` for history.

**Files:**
- Modify: `ucore`

```python
track_p = subparsers.add_parser("track", help="Track or show evaluation results")
track_p.add_argument("--npc-key", help="NPC key")
track_p.add_argument("--model", help="Model GGUF path")
track_p.add_argument("--show", action="store_true", help="Show evaluation history")
track_p.add_argument("--win-rate", type=float, help="Win rate (0-1)")
track_p.add_argument("--avg-quality", type=float, help="Average quality score")
track_p.add_argument("--val-loss", type=float, help="Validation loss")
track_p.add_argument("--notes", default="", help="Notes")
```

Handler:

```python
elif args.command == "track":
    if args.show:
        cmd = [PYTHON, str(SCRIPTS_DIR / "track_eval_results.py"), "--show"]
        if args.npc_key: cmd.extend(["--npc-key", args.npc_key])
        run_cmd(cmd)
    else:
        if not args.npc_key:
            print("Error: --npc-key required for tracking (or use --show)")
            sys.exit(1)
        cmd = [PYTHON, str(SCRIPTS_DIR / "track_eval_results.py"), "--track"]
        cmd.extend(["--npc-key", args.npc_key])
        if args.model: cmd.extend(["--model", args.model])
        if args.win_rate: cmd.extend(["--win-rate", str(args.win_rate)])
        if args.avg_quality: cmd.extend(["--avg-quality", str(args.avg_quality)])
        if args.val_loss: cmd.extend(["--val-loss", str(args.val_loss)])
        if args.notes: cmd.extend(["--notes", args.notes])
        run_cmd(cmd)
```

---

### Task 4: Add `ucore compare-runs` subcommand

**Objective:** Compare two runs by run_id rather than GGUF path. Resolves paths from manifests, runs evaluate.py, auto-links results.

**Files:**
- Create: `scripts/compare_runs.py` — New script
- Modify: `ucore` — add subcommand
- Modify: `_config/paths.py` — add helper to find GGUF from run_id

**The `scripts/compare_runs.py` script:**

```python
#!/usr/bin/env python3
"""compare_runs.py — Compare two training runs by run_id.

Resolves run manifests, finds the exported GGUF, and runs evaluate.py
side-by-side comparison. Saves results to eval/comparisons/.

Usage:
    python scripts/compare_runs.py chemistry_instructor \\
        --baseline-run 20260512_llama-3b-fast_001 \\
        --candidate-run 20260512_llama-3b-quality_001
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from _config import paths


def find_gguf_for_run(npc_key, run_id):
    """Find the best matching GGUF for a given run."""
    run_dir = paths.run_dir(npc_key, run_id)
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        sys.exit(1)
    
    # Read run manifest for model info
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        print(f"Error: No run_manifest.json in {run_dir}")
        sys.exit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    model_id = manifest.get("model_id", "unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
    
    # Look for GGUF in exports/{npc_key}/
    export_dir = paths.export_dir(npc_key)
    if not export_dir.exists():
        print(f"Error: No exports directory for {npc_key}")
        sys.exit(1)
    
    # Find q4_k_m GGUF (preferred) or any GGUF for this model
    ggufs = sorted(export_dir.glob(f"{npc_key}-*"))
    if not ggufs:
        # Try with explicit model_short
        model_short = paths.model_short_name(model_id)
        ggufs = sorted(export_dir.glob(f"{npc_key}-{model_short}-*.gguf"))
    
    if not ggufs:
        print(f"Error: No GGUF found for {npc_key} in {export_dir}")
        print(f"       Export first: ./ucore export {npc_key}")
        sys.exit(1)
    
    return str(ggufs[0]), model_id


def main():
    parser = argparse.ArgumentParser(description="Compare two training runs by run_id")
    parser.add_argument("npc_key", help="NPC key")
    parser.add_argument("--baseline-run", required=True, help="Baseline run ID")
    parser.add_argument("--candidate-run", required=True, help="Candidate run ID")
    parser.add_argument("--spec", help="Subject spec (auto-detected if omitted)")
    parser.add_argument("--num-questions", type=int, default=10)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--output", help="Output report path")
    args = parser.parse_args()
    
    # Resolve GGUF paths
    baseline_gguf, model_id = find_gguf_for_run(args.npc_key, args.baseline_run)
    candidate_gguf, _ = find_gguf_for_run(args.npc_key, args.candidate_run)
    
    # Auto-detect spec
    spec_path = args.spec
    if not spec_path:
        spec_guess = PROJECT_ROOT / "subjects" / f"{args.npc_key}.json"
        if spec_guess.exists():
            spec_path = str(spec_guess)
    
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
        from datetime import date
        today = date.today().isoformat()
        args.output = str(report_dir / f"{args.npc_key}_{args.baseline_run}_vs_{args.candidate_run}_{today}.md")
    
    cmd.extend(["--output", args.output])
    cmd.append("--track")
    
    print(f"Comparing runs for {args.npc_key}")
    print(f"  Baseline:  {args.baseline_run} → {baseline_gguf}")
    print(f"  Candidate: {args.candidate_run} → {candidate_gguf}")
    print(f"  Output:    {args.output}")
    print()
    
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
    print(f"\nComparison complete: {args.output}")


if __name__ == "__main__":
    main()
```

**Add `ucore compare-runs` subparser:**

```python
cr_p = subparsers.add_parser("compare-runs", help="Compare two training runs by run_id")
cr_p.add_argument("npc_key", help="NPC key")
cr_p.add_argument("--baseline-run", required=True, help="Baseline run ID")
cr_p.add_argument("--candidate-run", required=True, help="Candidate run ID")
cr_p.add_argument("--spec", help="Subject spec (auto-detected if omitted)")
cr_p.add_argument("--num-questions", type=int, default=10)
cr_p.add_argument("--judge", action="store_true")
```

**Handler:**

```python
elif args.command == "compare-runs":
    cmd = [PYTHON, str(SCRIPTS_DIR / "compare_runs.py"), args.npc_key]
    cmd.extend(["--baseline-run", args.baseline_run])
    cmd.extend(["--candidate-run", args.candidate_run])
    if args.spec: cmd.extend(["--spec", args.spec])
    if args.num_questions: cmd.extend(["--num-questions", str(args.num_questions)])
    if args.judge: cmd.append("--judge")
    run_cmd(cmd)
```

---

### Task 5: Add eval preset concepts (eval-profile config)

**Objective:** Define quick/smoke/full eval profiles so users can run `./ucore evaluate --preset smoke` instead of remembering flag combinations.

**Files:**
- Create: `configs/eval-presets.yaml` — profile definitions

Sample profiles:

```yaml
# configs/eval-presets.yaml
smoke:
  description: "Fast smoke test — 3 generic questions, no judge"
  num_questions: 3
  judge: false
  report_html: false

quick:
  description: "Quick check — 10 validation questions, no judge"
  num_questions: 10
  judge: false
  report_html: false

full:
  description: "Full evaluation — 25 questions, LLM judge, HTML report"
  num_questions: 25
  judge: true
  report_html: true
```

Then update evaluate.py to accept `--preset` which reads from this file.

---

### Task 6: Promotion gate for "best" symlink

**Objective:** The `best` symlink should only update if the model passes quality thresholds — not just lowest loss. This prevents garbage models from being promoted.

**Files:**
- Modify: `scripts/train.py` — add promotion gate after best-symlink logic
- Create: `configs/promotion-rules.yaml` — threshold definitions

**promotion-rules.yaml:**
```yaml
# configs/promotion-rules.yaml
# A model must pass ALL thresholds before being promoted to "best"
thresholds:
  max_training_loss: 1.5        # Reject if loss > 1.5
  min_eff_batch_size: 4         # Reject if effective batch size < 4
  min_train_examples: 10        # Reject if fewer than 10 training examples
```

**In train.py, gate the best-symlink update:**

```python
def check_promotion_rules(training_loss, config, num_train_examples) -> tuple[bool, list[str]]:
    """Check if the model meets minimum quality thresholds for promotion."""
    rules_path = PROJECT_ROOT / "configs" / "promotion-rules.yaml"
    if not rules_path.exists():
        return True, []  # No rules file = no gate
    
    with open(rules_path) as f:
        rules = yaml.safe_load(f)
    
    thresholds = rules.get("thresholds", {})
    failures = []
    
    max_loss = thresholds.get("max_training_loss")
    if max_loss is not None and training_loss > max_loss:
        failures.append(f"Training loss {training_loss:.4f} exceeds max {max_loss}")
    
    min_batch = thresholds.get("min_eff_batch_size")
    if min_batch is not None:
        eff = config.get("training", {}).get("batch_size", 1) * config.get("training", {}).get("gradient_accumulation_steps", 8)
        if eff < min_batch:
            failures.append(f"Effective batch size {eff} < min {min_batch}")
    
    min_examples = thresholds.get("min_train_examples")
    if min_examples is not None and num_train_examples < min_examples:
        failures.append(f"Training examples {num_train_examples} < min {min_examples}")
    
    return len(failures) == 0, failures
```

Then gate the best-symlink block: if promotion rules fail, print warning and don't update `best`.

---

### Task 7: Update EVALUATION_WORKFLOW.md

**Files:**
- Modify: `docs/EVALUATION_WORKFLOW.md`

Add sections for:
- New ucore commands: evaluate, quick-eval, track, compare-runs
- Eval presets (smoke/quick/full)
- Promotion rules and gating
- Comparison by run_id workflow

---

## Verification

```bash
# 1) All Python files compile
python -m py_compile scripts/compare_runs.py scripts/evaluate.py scripts/quick_eval.py scripts/track_eval_results.py

# 2) ucore shows new commands
./ucore --help  # Should list: evaluate, quick-eval, track, compare-runs

# 3) Promotion rules compile
python -c "import yaml; yaml.safe_load(open('configs/promotion-rules.yaml'))"

# 4) Commit
git add -A && git commit -m "feat: Phase 5 evaluation framework with CLI and compare-runs"
```
