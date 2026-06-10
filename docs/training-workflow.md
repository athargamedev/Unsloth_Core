# Unsloth Core Training Workflow

> Last updated: 2026-06-10 — major cleanup: removed deprecated Onyx/docs references, deduplicated content, aligned with current pipeline.

## Overview

The Unsloth Core training pipeline transforms an NPC subject specification into a playable GGUF-quantized LoRA model ready for Unity deployment. The pipeline follows seven canonical stages:

```
Subject Spec → [Validate] → [Generate] → [Sanitize] → [Dataset Eval] → [Train + Export] → [Evaluate]
```

**Preferred entrypoint — target workflow runner:**
```bash
./ucore target plan --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate
./ucore target run --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate --resume
```

This state-aware runner plans and executes the canonical stages with cache, lineage, GPU policy, and artifact checks. Use the manual commands below only for advanced recovery or debugging.

> **Pipeline Manifest:** Each stage auto-records to `var/.pipeline/run_manifest.json` via `record_pipeline_stage()`.
>
> **Environment:** All pipeline scripts auto-load `.env.local` via `src/core/ops/env_loader.py` — no manual `export` needed.

---

## 1. Pipeline Stages

### Stage 0: Validate Spec

**Entry point:** `./ucore validate-spec <spec>`
**Script:** `src/core/dataset/validate_subject_spec.py`

Validates the subject spec JSON before generation. Flags:
- `--generation-ready`: All checks combined (reference doc, categories, minimums)
- `--require-reference-docs`: Reference doc exists and is readable
- `--require-dataset-minimums`: All categories meet minimum counts

```bash
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec --all --json                              # audit all specs
```

---

### Stage 1: Generate Dataset

**Production entry points:**

| Method | CLI | Description |
|--------|-----|-------------|
| Ollama | `./ucore generate-ollama <spec>` | **Primary.** Uses Ollama models (qwen2.5:7b default) |
| Direct llama.cpp | `./ucore generate-local --model <gguf> <spec>` | More GPU/params control, auto-starts llama-server |

**Script:** `src/core/dataset/generate_dataset.py`

Reads NPC spec JSON and produces a ChatML-format Q&A dataset (72 examples: 8 identity + 32 teaching + 16 dialogue + 8 quest + 8 refusal).

```bash
# Production grounded generation (Ollama)
./ucore generate-ollama data/npcs/specs/history_guide.json --model qwen2.5:7b --fresh

# Direct llama.cpp generation
./ucore generate-local --model ~/models/qwen2.5-7b.gguf data/npcs/specs/history_guide.json --fresh

# Smoke/dev only — template
# ./ucore generate data/npcs/specs/history_guide.json --technique template
```

**Output:** `data/datasets/{npc_key}/{technique}/train.jsonl`

**Key concepts:**
- **`./ucore generate`** is marked `[LEGACY]` — only use `--technique template` for smoke tests
- **`generate-ollama`** defaults: model `qwen2.5:7b`, batch-size 4, temperature 0.6, val-split 0.12
- **`generate-local`** auto-starts/stops llama.cpp with tuned flags (gpu-layers 24, ctx-size 8192)
- The Ollama ↔ OpenAI compatibility layer detects URL format automatically:
  - `/api/chat` → Ollama format
  - `/v1/chat/completions` → OpenAI format

---

### Stage 2: Sanitize Dataset

**Entry point:** `./ucore sanitize <input>`
**Script:** `src/core/dataset/sanitize_dataset.py`

Validates dataset integrity:
- Confirms ChatML format (role/content turn structure)
- Strips leading/trailing whitespace on content fields
- Ensures no empty messages
- Deduplicates by content hash
- Scores and optionally discards low-quality examples
- Auto-repairs missing metadata (configurable)

```bash
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
```

**Output:** `{input_path}_clean.jsonl`

**Pipeline sanitize** always passes `--strict-canonical` and `--require-complete-metadata`. Template smoke runs may opt out with `--allow-metadata-repair`.

---

### Stage 3: Dataset Quality Eval

**Entry point:** `./ucore dataset-eval <spec>`
**Script:** `src/core/dataset/dataset_eval.py`

Runs the DeepEval suite against the sanitized dataset before training. This is the local build-loop quality gate.

```bash
./ucore dataset-eval data/npcs/specs/history_guide.json \
  --technique template --mode fast --judge-model qwen2.5:7b --cases-per-category 1
```

**Parameters:**
- Judge: `qwen2.5:7b` via Ollama, temperature 0
- Mode: `fast` (1 row/category, diagnostic) or `release` (5 rows/category, blocking)
- Confident AI: auto-uploads when `CONFIDENT_API_KEY` is set

**Outputs:**
- `data/datasets/{npc_key}/{technique}/quality_summary.json`
- `data/datasets/{npc_key}/{technique}/quality_failures.json`

**Quality gate enforcement (in `train.py`):**
Training is blocked by default unless:
- Dataset is `train_clean.jsonl`, not raw `train.jsonl`
- `quality_summary.json` exists with `status: "ok"`
- Zero distribution gaps, unknown rows, clean sanitizer signals, matching content hash
- `release` mode: zero failing DeepEval cases; `fast` mode: diagnostic only

Pass `--allow-ungated-dataset` to bypass (dev-only).

---

### Stage 4: Training

**Entry point:** `./ucore train <spec>`
**Script:** `src/core/training/train.py`

Uses Unsloth's `SFTTrainer` with LoRA for parameter-efficient fine-tuning.

```bash
./ucore train data/npcs/specs/history_guide.json --technique ollama --preset fast-3b --export-gguf
```

**Config hierarchy:**
```
Spec-derived base → Preset override (etc/presets/*.yaml) → CLI override (--flags)
```

**Active presets:**

| Preset | Model | LoRA rank | Epochs | Effective batch | When to use |
|--------|-------|:---------:|:------:|:---------------:|-------------|
| `smoke` | LLaMA 3.2 1B | 8 | 1 | 2 | Debugging/testing |
| `fast-3b` | LLaMA 3.2 3B | 16 | 3 | 8 | Standard NPC training (6GB GPU) |
| `fast-1.7b` | Qwen3 1.7B | 16 | 3 | 4 | 6GB GPU, smaller model |
| `safe-any` | Auto-detect | 8 | 3 | 8 | CUDA OOM fallback |
| `premium-3b` | 3B | 32 | 3 | 16 | 15GB+ VRAM (T4/L4) |
| `remote-3b-quality` | 3B | 64 | 5 | 16 | Colab/remote, max quality |

**Output:** `artifacts/models/{npc_key}/runs/{run_id}/` (LoRA adapter weights)

**GPU notes (RTX 3060 6GB):** `fast-3b` tuned with `packing: true`, `batch_size: 1`, `gradient_accumulation_steps: 8`. Preflight may auto-downgrade `fast-3b` to `safe-any` if VRAM < 10GB.

**Export flag:** `--export-gguf` exports adapter GGUF automatically after training (no separate step).
Output: `artifacts/exports/{npc_key}/{npc_key}-lora-f16.gguf`

---

### Stage 5: Model Evaluation

**Entry point:** `./ucore evaluate`
**Script:** `src/core/evaluation/evaluate.py`

Compares two models (baseline vs candidate) with optional LLM judge.

```bash
# Side-by-side comparison (baseline + candidate as LoRA adapters)
./ucore evaluate \
  --baseline artifacts/exports/history_guide/round1/history_guide-lora-f16.gguf \
  --candidate artifacts/exports/history_guide/history_guide-lora-f16.gguf \
  --base-model /path/to/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec data/npcs/specs/history_guide.json \
  --report-html --feedback-json artifacts/eval/results/feedback/history_guide.json

# Standalone measurement
./ucore evaluate --baseline artifacts/exports/history_guide/history_guide-lora-f16.gguf \
  --spec data/npcs/specs/history_guide.json --report-html
```

**Key details:**
- Starts two `llama-server` instances (baseline on 8888, candidate on 8889) with `--lora`
- Both baseline and candidate can be LoRA adapters loaded on top of `--base-model`
- Same mechanism as LLMUnity runtime: base GGUF + LoRA via llama.cpp
- Validates: sentence count, name mention, AI disclaimers, think tags
- Quality metrics: lexical diversity (TTR), repetition rate, response length
- Optional LLM judge for semantic comparison (default `qwen2.5:7b`)
- `--gpu-layers 0` forces CPU fallback (useful when GPU OOMs)

**Output:**
- HTML report with Chart.js
- Structured feedback JSON with per-concept win rates, quality scores

---

### Stage 6: Feedback Loop

**Entry point:** `./ucore feedback <feedback.json>`
**Script:** `src/core/training/feedback_loop.py`

Closes the loop between evaluation and dataset generation:

1. Analyze feedback JSON → identify weak concepts (win_rate < 0.5, quality > 25, violations > 1)
2. Determine gap type:
   - **training_density**: Regenerate more examples with `--concept-focus`
   - **knowledge_gap**: Add reference doc content
3. Regenerate → sanitize → dataset-eval → retrain → re-evaluate

```bash
./ucore feedback artifacts/eval/results/feedback/<npc>.json --auto
./ucore feedback artifacts/eval/results/feedback/<npc>.json --dry-run   # analyze only
```

**Strategy integration:** The `npc-production-grounded` profile defines anti-loop rules — after bounded repair cycles, routes fix to shared pipeline/presets.

---

## 2. Canonical paths

| Artifact | Path |
|----------|------|
| Specs | `data/npcs/specs/<npc>.json` |
| Reference docs | `data/npcs/reference_docs/<npc>_primer.md` |
| Datasets | `data/datasets/<npc>/<technique>/` |
| Clean train file | `data/datasets/<npc>/<technique>/train_clean.jsonl` |
| Training runs | `artifacts/models/<npc>/runs/<run_id>/` |
| Pointers | `artifacts/models/<npc>/best`, `artifacts/models/<npc>/latest` |
| GGUF adapters | `artifacts/exports/<npc>/<npc>-lora-f16.gguf` |
| Eval reports | `artifacts/eval/reports/<npc>/` |
| Feedback JSON | `artifacts/eval/results/feedback/<npc>.json` |

---

## 3. Data flow diagram

```
data/npcs/specs/{npc}.json ──── data/npcs/reference_docs/{npc}_primer.md
          │
          ▼
  ./ucore generate-ollama <spec>                    # or generate-local
          │
          ▼
  src/core/dataset/generate_dataset.py ──► Ollama API / llama.cpp
          │
          ▼
  data/datasets/{npc}/{technique}/train.jsonl
          │
          ▼
  src/core/dataset/sanitize_dataset.py ──► train_clean.jsonl
          │
          ▼
  src/core/dataset/dataset_eval.py ──► quality_summary.json (gate)
          │
          ▼
  src/core/training/train.py ──► etc/presets/*.yaml
          │
          ▼
  artifacts/models/{npc}/runs/{run_id}/  (LoRA adapter)
          │
          ▼
  (built-in --export-gguf) src/core/export/export.py
          │
          ▼
  artifacts/exports/{npc}/{npc}-lora-f16.gguf
          │
          ▼
  src/core/evaluation/evaluate.py ──► eval reports + feedback JSON
          │
          ▼
  Unity Assets/StreamingAssets/Models/{npc}-lora-f16.gguf
```

---

## 4. Dataset contracts

Defined in `src/core/dataset/dataset_contracts.py`:

| Category | Min examples | Description |
|----------|:-----------:|-------------|
| `identity` | 8 | Persona introduction |
| `teaching` | 32 | Subject-matter explanations |
| `dialogue` | 16 | Natural conversation handling |
| `quest` | 8 | Scenario-based interactions |
| `refusal` | 8 | Safe boundary responses |
| **Total** | **72** | |

**Difficulty levels:** `beginner`, `intermediate`, `advanced`

**Helpers:** `expected_examples_per_category()`, `calculate_distribution_gaps()`, `summarize_jsonl_dataset()`, `file_sha256()`

---

## 5. Config hierarchy

Training configs build from three layers:

1. **Spec-derived base** — detected from `data/npcs/specs/{npc}.json`, canonical dataset path, and default Llama 3.2 3B model
2. **Preset** (`etc/presets/{name}.yaml`) — hyperparameter overrides
3. **CLI flags** (`--lr`, `--epochs`, `--wandb`, etc.) — highest priority

```bash
./ucore train data/npcs/specs/history_guide.json --preset fast-3b --wandb --export-gguf
```

Example preset (`fast-3b.yaml`):
```yaml
training:
  batch_size: 1
  gradient_accumulation_steps: 8
lora:
  lora_r: 16
  lora_alpha: 32
```

---

## 6. Quality gate summary

| Check | Blocks training? |
|-------|:----------------:|
| Dataset is `train_clean.jsonl` (not raw `train.jsonl`) | Yes |
| `quality_summary.json` exists with `status: "ok"` | Yes |
| Zero distribution gaps | Yes |
| Zero unknown rows | Yes |
| Clean sanitizer quality signals | Yes |
| Matching dataset content hash | Yes |
| Failing DeepEval cases (`release` mode) | Yes |
| Failing DeepEval cases (`fast` mode) | No (diagnostic) |

**Bypass:** `--allow-ungated-dataset` (dev-only)

---

## 7. Ollama model presets

Configuration: `etc/ollama/model-presets.yaml`
Resolver: `src/core/ops/ollama_model_presets.py`

| Preset | Model | Use |
|--------|-------|-----|
| `generate-qwen25` | `qwen2.5:7b` | Default generation |
| `generate-llama31` | `llama3.1:8b` | Alternative |
| `judge-qwen25` | `qwen2.5:7b` | Default local judge |
| `judge-llama31-exp` | `llama3.1:8b` | Experimental judge |

**Resolution priority:**
1. Explicit `--model` flag
2. Named `--preset` (maps through YAML)
3. Role-specific default preset
4. Safety fallback (`qwen2.5:7b`)

---

## 8. Preflight system

**Script:** `src/core/ops/preflight.py`
**CLI:** `./ucore audit check`

Checks performed before expensive pipeline stages:

| Check | Description |
|-------|-------------|
| GPU memory | `nvidia-smi` free/total VRAM |
| Auto-downgrade | `fast-3b` → `safe-any` when VRAM < 10GB |
| Ollama auto-unload | Stop running Ollama models to free VRAM |
| GCC toolchain | Verify `gcc` available for Triton |

Preflight returns status: `ok`, `degraded`, or `blocked`.

---

## 9. Output artifacts

| Stage | Output path | Format |
|-------|-------------|--------|
| Validate | (exit code only) | — |
| Generate | `data/datasets/{npc}/{technique}/train.jsonl` | JSONL (ChatML) |
| Sanitize | `data/datasets/{npc}/{technique}/train_clean.jsonl` | JSONL (cleaned) |
| Dataset eval | `data/datasets/{npc}/{technique}/quality_summary.json` | JSON |
| Train | `artifacts/models/{npc}/runs/{run_id}/` | LoRA (SafeTensors) |
| Export | `artifacts/exports/{npc}/{npc}-lora-f16.gguf` | GGUF (adapter) |
| Evaluate | `artifacts/eval/reports/{npc}/eval_*.html` | HTML (Chart.js) |
| Evaluate | `artifacts/eval/results/feedback/{npc}_*.json` | JSON (per-concept) |

---

## 10. Available training presets (full)

| Param | Base | `smoke` | `fast-3b` | `fast-1.7b` | `safe-any` | `premium-3b` | `remote-3b-quality` |
|-------|:----:|:-------:|:---------:|:-----------:|:----------:|:------------:|:-------------------:|
| GPU target | 6GB | any | 6GB | 6GB | any | 15GB+ | Colab |
| Model | Llama-3.2-3B | *inherits* | *inherits* | *inherits* | *inherits* | *inherits* | Llama-3.2-3B |
| num_epochs | 3 | 1 | 3 | 3 | 3 | 3 | 5 |
| batch_size | 1 | 1 | 1 | 1 | 1 | 4 | 4 |
| gradient_accum | 8 | 2 | 8 | 4 | 8 | 4 | 4 |
| effective batch | 8 | 2 | 8 | 4 | 8 | 16 | 16 |
| max_seq_length | 2048 | 512 | 2048 | 1024 | 1024 | 2048 | 2048 |
| LoRA r | 16 | 8 | 16 | 16 | 8 | 32 | 64 |
| LoRA alpha | 32 | 16 | 32 | 32 | 16 | 64 | 128 |
| LoRA dropout | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.05 | 0.05 |
| learning_rate | 2e-4 | 2e-4 | 2e-4 | 2e-4 | 2e-4 | 2e-4 | 1.5e-4 |

---

## 11. Related documentation

| Document | Purpose |
|----------|---------|
| `AGENTS.md` | Project overview, hard rules, quick start |
| `docs/project-state.md` | Current NPC run state |
| `docs/platform-integration.md` | Platform roles, credentials, naming conventions |
| `docs/reference/cli-commands.md` | Full CLI reference |
| `docs/reference/subject-spec.md` | NPC spec JSON schema |
| `docs/guides/operator-runbook.md` | Quick human reference |
