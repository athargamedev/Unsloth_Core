# Pipeline Review & Efficient Full Workflow Plan

## Source Report
`docs/reports/end-to-end-pipeline-test-20260606.md` — full E2E test from 2026-06-06 for `history_guide` + `chef_assistant`.

## Goal
Run a clean full pipeline (validate → generate → sanitize → gate → train → export → evaluate) for both active NPCs, fixing known bugs, avoiding VRAM death, and producing final evaluation HTML reports — in minimal wall-clock time.

---

## Step 0 — Patch Stale Code (do this before anything)

### 0a. Fix dataset_eval.py output path
`src/core/dataset/dataset_eval.py:107` hardcodes `subjects/datasets/` instead of using the canonical `data/datasets/`. The config in `src/config/paths.py:108` already handles the migration — the local override in `dataset_eval.py` bypasses it.

**Edit:** Change `dataset_dir()` to use `src.config.paths.dataset_root()`.

Also fix error message at lines 607-608 that references old path.

### 0b. Clear stale artifacts
```bash
rm -rf subjects/datasets/{history_guide,chef_assistant}/ollama/quality_*.json
rm -rf unsloth_compiled_cache/
```

### 0c. Verify VRAM baseline
```bash
sudo systemctl stop ollama
nvidia-smi
```
Ensure ~6GB free before starting.

### 0d. Verify existing fixes are still in place
- `train.py:944` → `eval_strategy="no"` ✅
- `train.py:809` → `device_map=0` ✅
- `ollama_orchestrator.py` → lazy `ProgressTracker` import ✅

---

## Step 1 — Validate Specs

```bash
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

---

## Step 2 — Generate Datasets (both NPCs, sequential — Ollama uses 1 slot)

```bash
./ucore generate-ollama data/npcs/specs/history_guide.json \
  --model qwen2.5:7b --fresh --temperature 0.6

./ucore generate-ollama data/npcs/specs/chef_assistant.json \
  --model qwen2.5:7b --fresh --temperature 0.6
```

**Efficiency wins over last run:**
- Temperature 0.6 reduces guardrail rejections (was 22min for chef at higher temp)
- Chef had 100% success rate last time; fine-tuning temp may keep it high while cutting retries

**Verify after:** refusal rows are present (chef had shortfall of 4 last time). If shortfall persists, note for quality gate.

---

## Step 3 — Sanitize (both NPCs)

```bash
./ucore sanitize data/datasets/history_guide/ollama/train.jsonl \
  --output data/datasets/history_guide/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

./ucore sanitize data/datasets/chef_assistant/ollama/train.jsonl \
  --output data/datasets/chef_assistant/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
```

After Step 0 patch, quality artifacts will write to `data/datasets/` correctly.

---

## Step 4 — Dataset Quality Gate (both NPCs)

```bash
./ucore dataset-eval data/npcs/specs/history_guide.json \
  --technique ollama --mode fast --judge-model qwen2.5:7b

./ucore dataset-eval data/npcs/specs/chef_assistant.json \
  --technique ollama --mode fast --judge-model qwen2.5:7b
```

**Gate failure expectation:** Fast mode (1 case/category) likely produces `structural_failure` on identity/refusal again. Accept this. Use `--allow-ungated-dataset` on train step.

**VRAM note:** DeepEval uses Ollama for judging. If we want to avoid VRAM pressure, could switch judge to qwen2.5:3b here too.

---

## Step 5 — Train + Export (both NPCs)

```bash
./ucore train data/npcs/specs/history_guide.json \
  --technique ollama --preset fast-3b --export-gguf

./ucore train data/npcs/specs/chef_assistant.json \
  --technique ollama --preset fast-3b \
  --allow-ungated-dataset --export-gguf
```

**Critical:**
- `eval_strategy="no"` prevents `convert_to_fp32` OOM ✅
- `device_map=0` prevents device map to auto fallback ✅
- batch=1, grad_accum=8, max_seq_len=1024 fits 6GB ✅
- Export writes to `artifacts/exports/{npc}/{npc}-lora-f16.gguf` ✅

**Watch for:** CUDA OOM at `trainer.save_model()` (step 1047). This should work since we skip `trainer.evaluate()`.

---

## Step 6 — Evaluate: Generate Final Reports (the missing step from last run)

### 6a. VRAM juggling

Last run failed at this step because:
1. Too many tool calls consumed budget before getting here
2. VRAM contention between llama-server (base GGUF eval) and Ollama (judge)
3. No strategy for sequencing stop/load/eval cycles

**Solution for 6GB:**
1. Stop Ollama: `sudo systemctl stop ollama` — frees ~4.7GB
2. Evaluate uses llama-server for base model + adapter inference
3. Evaluate uses Ollama for LLM judge. With Ollama stopped, fall back to **heuristic-only mode** (`./ucore evaluate` without `--judge`) OR use a small judge

**Recommended approach — heuristic-only eval (avoids VRAM contention entirely):**

```bash
# Stop Ollama first
sudo systemctl stop ollama

# History Guide — heuristic eval (no LLM judge needed)
./ucore evaluate \
  --baseline .models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --candidate artifacts/exports/history_guide/history_guide-lora-f16.gguf \
  --base-model .models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec data/npcs/specs/history_guide.json \
  --report-html

# Chef Assistant — heuristic eval
./ucore evaluate \
  --baseline .models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --candidate artifacts/exports/chef_assistant/chef_assistant-lora-f16.gguf \
  --base-model .models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec data/npcs/specs/chef_assistant.json \
  --report-html
```

**Alternative — with LLM judge (qwen2.5:3b = 1.9GB VRAM):**
```bash
# Ensure Ollama running with small judge only
ollama pull qwen2.5:3b
sudo systemctl start ollama

./ucore evaluate \
  ...same args... \
  --report-html --judge --judge-model qwen2.5:3b
```

This should fit: llama-server base (~2.5GB) + qwen2.5:3b (~1.9GB) + overhead (~1.5GB) ≈ 5.9GB.

### 6b. What evaluate produces
- `artifacts/eval/reports/{npc}/` — HTML + Markdown comparison reports
- `artifacts/eval/results/feedback/{npc}.json` — structured feedback
- Win rates per category, constraint compliance scores, failure data

---

## Decision Points (choices to make before starting)

| Question | Options | Recommendation |
|----------|---------|----------------|
| Fresh datasets or reuse existing? | `--fresh` / no flag | Use `--fresh` — existing datasets are from 2026-06-06, want latest |
| Dataset gate mode | `fast` / `standard` | `fast` — standard uses too much VRAM on 6GB |
| Accept gate failures? | `--allow-ungated-dataset` / fix identity/refusal | Accept — fixing identity/refusal is a content improvement, not pipeline issue |
| Judge model for eval | `qwen2.5:7b` / `qwen2.5:3b` / heuristic-only | Heuristic-only for baseline (no VRAM contention). Then optionally qwen2.5:3b for LLM-judged reports |
| Parallelize NPCs? | sequential / background | Sequential — Ollama and GPU are single-slot resources on 6GB |

---

## Estimated Wall-Clock

| Phase | Time | Bottleneck |
|-------|------|------------|
| Pre-flight patching | ~2 min | Manual edits |
| Validate (2 NPCs) | ~2s | Near-instant |
| Generate (2 NPCs) | ~30 min | Chef assistant (~22 min is the slowest) |
| Sanitize (2 NPCs) | ~5s | Near-instant |
| Dataset gate (2 NPCs) | ~8 min | DeepEval + Ollama judge |
| Train (2 NPCs) | ~4 min | 70s guide + 158s chef |
| Export | 0 | Inline with `--export-gguf` |
| Evaluate (2 NPCs, heuristic) | ~10 min | llama-server inference |
| Evaluate (2 NPCs, LLM judge) | ~20 min | + judge scoring latency |
| **Total** | **~55 min (heuristic) / ~75 min (LLM judge)** | |

---

## Failure Mode Checklist

Before each phase:
- [ ] Ollama running for generate/gate, stopped for eval VRAM window
- [ ] `nvidia-smi` shows sufficient free VRAM
- [ ] No stale `unsloth_compiled_cache/`
- [ ] Quality artifacts writing to `data/datasets/` (not `subjects/datasets/`)
- [ ] `--allow-ungated-dataset` available for chef train step
- [ ] qwen2.5:3b pulled for eval judge (if using LLM judge mode)
