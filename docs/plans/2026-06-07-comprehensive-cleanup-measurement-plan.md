# Plan: Full Data Cleanup + Measurement Revival

## Why

The repo accumulated 53 NPC dataset versions, 7 model checkpoints per run, 15+ eval reports per NPC, old `subjects/` vs new `data/datasets/` split, template technique data mixed with production ollama data, and **zero systematic comparison pipeline** between runs. We have `compare_runs`, `promote`, `tb_reader`, `stage_gate`, `experiment_registry` — and use none of them.

This plan: (1) purge contamination, (2) freeze what works, (3) wire the forgotten measurement tools into the loop.

---

## Phase 0 — Audit & Map (what exists, what's stale)

### Step 0.1: Inventory all pipeline tools

| CLI tool | File | Used? | Status |
|---|---|---|---|
| `validate-spec` | dataset/validate_subject_spec.py | Yes | Active |
| `generate-ollama` | dataset/generate_dataset_ollama.py | Yes | Active |
| `sanitize` | dataset/sanitize_dataset.py | Yes | Active |
| `dataset-eval` | dataset/dataset_eval.py | Yes | Active |
| `train` | training/train.py | Yes | Active |
| `export` | export/export.py | Yes | Active |
| `evaluate` | evaluation/evaluate.py | Partial | Used ad-hoc, not systematic |
| `deploy` | export/deploy_to_unity.py | Occasional | Active |
| `tb-reader` | evaluation/tb_reader.py | **Never** | Dead — not in current workflow |
| `compare-runs` | evaluation/compare_runs.py | **Never** | Dead — canonical path to compare-runs+promote never used |
| `compare-local-models` | ops/compare_local_models.py | **Never** | Dead — model selection before generation |
| `compare-canonical-runs` | ops/compare_canonical_runs.py | **Never** | Dead — .pipeline/runs based |
| `promote` | ops/promote_model.py | **Never** | Dead — designed to consume compare-runs output |
| `history` | ops/run_index.py + `history` subcommand | **Never** | Dead |
| `registry` | ops/run_registry.py + `registry` subcommand | **Never** | Dead |
| `strategy` | ops/npc_production_strategy.py | Partial | Only for `density_repair_needed()` check |
| `stage-gate` | ops/stage_gate.py | **Never** | Dead — checksum verification between stages |
| `pipeline` | orchestration/plan_execution.py | **Never** | Dead — full auto-pipeline |
| `inference-server` | ops/inference_server.py | Occasional | Active |
| `confident-goldens` | dataset/confident_goldens.py | Once | Used once, not in current loop |
| `confident-classifiers` | ops/confident_classifiers.py | **Never** | Dead |
| `feedback` | training/feedback_loop.py | Deprecated in CLI | Replaced by dataset-eval |
| `repair` | CLI > dataset-eval --repair | Deprecated in CLI | Replaced by generate-ollama --repair |

### Step 0.2: Map all eval results per NPC (what's not been compared)

**history_guide**: 15 eval reports, 3 GGUF exports ever made (smoke_001 -> safe-any_004 -> fast-1.7b_002), 8+ dataset versions

**chef_assistant**: 2 eval reports, 1 GGUF export, many quality eval history snapshots

**marvel_heroes_instructor**: 3 eval reports, 1 GGUF export, 14 training runs (!), but **never promoted to active** — all runs exploratory

### Step 0.3: Identify stale/contaminating data patterns

- `data/datasets/*/template/` — template-generated data mixed alongside ollama data for same NPC → contamination risk
- `v20260603_*` old version snapshots in `history_guide` — 7 versions, all from old `subjects/`-era pipeline
- `artifacts/models/marvel_heroes_instructor/runs/*` — 14 training runs, none deployed, no best symlink, just `latest`
- `artifacts/models/history_guide/runs/20260531_smoke_*` — 3 smoke runs from old template datasets, **should not be compared against current ollama-trained runs**
- `train_test.jsonl`, `train_test_clean.jsonl` in history_guide — orphan test set (never used in eval)
- `quality_summary_fast_identity.json` in history_guide — orphan artifact name
- `*_bad*` files in marvel_heroes_instructor — leftover from comparison experiments
- `*_comp*` files in marvel_heroes_instructor — comparison data for models that were never promoted

---

## Phase 1 — Data Cleanup (purge contamination)

### Step 1.1: Freeze what's production-worthy

Before deleting anything, identify the **last good state** for each active NPC:

| NPC | Current production dataset | Current production model | Current GGUF export |
|---|---|---|---|
| history_guide | `data/datasets/history_guide/ollama/v20260607_044803/` | best→`20260607_fast-1.7b_llama3.2-3b_002` | `artifacts/exports/history_guide/history_guide-lora-f16.gguf` |
| chef_assistant | `data/datasets/chef_assistant/ollama/train_clean.jsonl` (latest gen) | best→`20260607_fast-1.7b_llama3.2-3b_004` | `artifacts/exports/chef_assistant/chef_assistant-lora-f16.gguf` |

### Step 1.2: Delete per NPC

**For history_guide (active):**
- `data/datasets/history_guide/template/` — entire dir (template data, never used for production)
- `data/datasets/history_guide/deepeval/` — entire dir (orphan technique)
- `data/datasets/history_guide/ollama/train_test.jsonl` + `train_test_clean.jsonl` — orphan test split
- `data/datasets/history_guide/ollama/quality_summary_fast_identity.json` — orphan artifact
- `data/datasets/history_guide/ollama/v20260603_*` — all 7 old snapshots (pre-migration datasets)
- `data/datasets/history_guide/ollama/v20260606_232740/` — old snapshot before latest gen
- `data/datasets/history_guide/ollama/history/*` — all history snapshots (keep only latest quality_report/quality_failures/quality_summary)

**For chef_assistant (active):**
- `data/datasets/chef_assistant/template/` — entire dir (template data)
- `data/datasets/chef_assistant/ollama/v20260603_151303/` — old snapshot
- `data/datasets/chef_assistant/ollama/v20260607_001005/` — old snapshot before latest gen
- `data/datasets/chef_assistant/ollama/history/*` — all history snapshots (keep only latest quality_report/quality_failures/quality_summary)

**For marvel_heroes_instructor (inactive):**
- Keep spec, keep reference docs, keep GGUF export for reference
- Delete all training runs (`artifacts/models/marvel_heroes_instructor/runs/*`)
- Delete old dataset versions (`data/datasets/marvel_heroes_instructor/ollama/v20260602_*`)
- Delete train_bad*, train_comp*, *_llama_comp*, *_qwen_comp* — orphan comparison artifacts
- Delete template technique data (`data/datasets/marvel_heroes_instructor/template/`)
- Keep evaluation reports in `artifacts/eval/reports/marvel_heroes_instructor/` for reference

### Step 1.3: Archive eval reports (keep last 2 per NPC)

For each `artifacts/eval/reports/<npc>/`, keep only the 2 most recent eval runs (`.md` + `.html` + `.index.json`). Archive the rest to a dated tarball.

---

## Phase 2 — Measurement Revival (wire the forgotten tools)

### Step 2.1: Make `tb-reader` the default loss reporter

**What it does**: Reads TensorBoard event files from training runs, outputs structured JSON with `{runId, scalars: {loss: [{step,value}...], eval_loss: [...]}}`.

**Why we forgot it**: `train.py` produces `training_metrics.json` manually but this is loss from the last step only — no curve. `tb-reader` gives the full loss curve.

**Action**: Add to `./ucore train` post-step (or as `--tb-summary` flag):
```
./ucore tb-reader --run-dir artifacts/models/<npc>/runs/<run_id>/
```
Returns JSON. Store in `artifacts/models/<npc>/runs/<run_id>/tb_metrics.json`.

### Step 2.2: Wire `compare-runs` into the promotion loop

**What it does**: Takes baseline_run_id + candidate_run_id, finds their GGUF exports, runs `evaluate.py` side-by-side, produces a comparison report, stores it.

**Why we forgot it**: `evaluate` was used ad-hoc against raw GGUF files (not linked to training runs). `compare-runs` links eval results back to run lineage.

**Execution order**: After training finishes, before any ad-hoc eval:
```bash
./ucore compare-runs <npc> \
  --baseline-run <best_run_id> \
  --candidate-run <new_run_id> \
  --judge qwen2.5:7b
```

**Decision rule**: If `compare-runs` reports `candidate` won → next step. If `baseline` won → flag for human review, don't auto-promote.

### Step 2.3: Wire `promote` as the gatekeeper

**What it does**: Reads comparison records, checks if candidate won, updates `best` symlink and export manifest.

**Why we forgot it**: No `compare-runs` output existed to consume.

**Action**: After `compare-runs` returns win for candidate:
```bash
./ucore promote --npc-key <npc> --candidate-run-id <run_id> --no-dry-run
```
This updates `artifacts/models/<npc>/best` → candidate run, triggers re-export if needed.

### Step 2.4: Wire `stage-gate` between pipeline stages

**What it does**: SHA256 checksums between stages to detect data corruption or manual edits between generate→sanitize→train→export.

**Why we forgot it**: No one remembered it existed.

**Action**: Add to `./ucore pipeline` full pipeline. Also useful as standalone:
```bash
./ucore stage-gate verify --stage sanitize --input data/datasets/<npc>/ollama/train_clean.jsonl
```

### Step 2.5: Use `compare-local-models` once per week

**What it does**: Benchmarks all local Ollama models on a shared prompt suite, ranks by latency + TPS + score.

**Why we forgot it**: We hard-coded `qwen2.5:7b` as judge and never re-evaluated.

**Action**: Run weekly or after any Ollama model pull:
```bash
./ucore compare-local-models --prompt-suite etc/judge-prompts.json
```
Compare results against `etc/ollama-model-presets.yaml`. If a newer model beats qwen2.5:7b on both quality and latency, update the default.

### Step 2.6: Use `history` to track win-rate trends

**What it does**: Queries the `.pipeline/runs_index.jsonl` for win-rate progression over time per NPC.

**Why we forgot it**: `.pipeline/runs.jsonl` is populated by `run_registry.start_run()` but nothing calls it.

**Action**: Every pipeline step (train, evaluate, compare-runs, promote) must call `RunRegistry`:
```bash
./ucore registry record --npc <npc> --stage evaluate --metrics '{"win_rate":0.72,"avg_quality":43.1}'
```
Then:
```bash
./ucore history --npc history_guide --metric win_rate --format chart
```
This surfaces whether we're actually improving NPC-by-NPC over time.

### Step 2.7: Use `tb-reader` to validate training quality

Before `compare-runs`, check training loss curve:
```bash
./ucore tb-reader --run-dir artifacts/models/<npc>/runs/<run_id>/
```
If `train/loss` final < 0.5 AND curve is monotonically decreasing → good candidate. If loss spikes at end → flag for human review, skip auto-promote.

---

## Phase 3 — Script Execution Order (the pipeline)

### Phase 3-A: Cleanup Script (one-shot)

```
1. `rm -rf data/datasets/*/template/`           # Remove all template data
2. `rm -rf data/datasets/history_guide/deepeval/` # Remove orphan technique
3. `rm -f data/datasets/history_guide/ollama/train_test*`  # Orphan test split
4. `rm -f data/datasets/history_guide/ollama/quality_summary_fast_identity*`
5. Archive old dataset versions to /tmp/old-versions-archive/ (keep latest V only):
   - history_guide: v20260603_*, v20260606_232740
   - chef_assistant: v20260603_151303, v20260607_001005
   - marvel_heroes_instructor: v20260602_*
6. Archive old model runs to /tmp/old-runs-archive/:
   - marvel_heroes_instructor: all runs
   - history_guide: 20260531_smoke_*, 20260601_smoke_*, 20260601_fast-3b_* (pre-dataset-migration)
   - chef_assistant: (keep only best/latest)
7. Archive old eval reports (keep last 2 per NPC)
8. Archive orphan comparison files in marvel_heroes_instructor (train_bad*, train_comp*)
```

### Phase 3-B: Measurement Script (run per training cycle)

For each NPC training cycle, execution order:

```
Step 1: `tb-reader` on run directory → store tb_metrics.json in run dir
        FAIL CONDITION: loss_final > 0.5 OR loss_spikes_at_end → STOP, human review

Step 2: `compare-runs` baseline vs candidate → write comparison report
        FAIL CONDITION: candidate did NOT win → STOP, no promote

Step 3: `promote` candidate → update best symlink, trigger re-export
        FAIL CONDITION: promote checks fail → human review

Step 4: `registry record` stage=compare with metrics → append to runs_index.jsonl

Step 5: `history` query → print win_rate progression chart
```

### Phase 3-C: Weekly Health Script

```
1. `compare-local-models` → check if judge model should be updated
2. `history --npc history_guide --metric win_rate --limit 20`
   → check if win rate is trending up or plateauing
3. `history --npc chef_assistant --metric win_rate --limit 20`
   → same check
4. `stage-gate verify` for last production run of each NPC
   → detect corrupted/interrupted pipeline artifacts
```

---

## Phase 4 — What's Missing Entirely

### 4.1: No baseline lock-in

Every comparison in `evaluate.py` uses whatever GGUF you pass as `--baseline`. There's no enforced notion of "the current production baseline is X". **Action**: `best` symlink + `artifacts/exports/<npc>/manifest.json` must be the source of truth for "what is the current production adapter".

### 4.2: No "regression gate"

If a new dataset is worse than the previous one (win_rate falls below threshold), we should **block promotion** and flag the dataset, not the training params. This needs a **dataset-level comparison** step (evaluate old dataset vs new dataset on the same model).

### 4.3: No unified eval results database

Currently `track_eval_results.py` stores to Supabase but the fallback is JSON files in `artifacts/eval/results/`. These are never queried in aggregate. **Action**: Build a simple SQLite aggregate or use `.pipeline/runs.jsonl` as the single source of truth.

### 4.4: No `pipeline` auto-run

`./ucore pipeline` exists but is never used. It chains generate→sanitize→dataset-eval→train→export→evaluate. We run each step manually. **Action**: Once measurement tools are wired, test `./ucore pipeline` in dry mode.

---

## Measurement Diagram

```
  GENERATE ──→ SANITIZE ──→ DATASET-EVAL ──→ TRAIN ──→ EXPORT ──→ EVALUATE
       │            │              │              │          │          │
       │            │              │              │          │          │
       ▼            ▼              ▼              ▼          ▼          ▼
  stage_gate  stage_gate     stage_gate     tb_reader   stage_gate   compare-runs
  (checksum)  (checksum)     (checksum)     (loss       (checksum)   (baseline vs
                                              curve)                  candidate)
                                                                        │
                                                                        ▼
                                                                   promote (if won)
                                                                        │
                                                                        ▼
                                                                   registry record
                                                                        │
                                                                        ▼
                                                                   history query
```

---

## Success Criteria

1. Each NPC has exactly **one active dataset version** (the `latest` symlink) — no orphan snapshot dirs
2. Each NPC has exactly **one GGUF export** for production (in `artifacts/exports/`)
3. `history --npc * --metric win_rate` returns non-empty, monotonic improvement
4. Every training run is auditable: `tb-reader` loss curve → `compare-runs` result → `promote` decision → `registry` record
5. `stage-gate` checks pass for the last production run of each NPC
6. Pre-commit hooks pass clean (ruff/ruff-format/end-of-file-fixer)
