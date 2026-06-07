# Unsloth Core Training Workflow

## Overview

The preferred agent/operator entrypoint is the target workflow runner:

```bash
./ucore target plan --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate
./ucore target run --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate --resume
```

This state-aware runner plans and executes the canonical stages with cache, lineage,
GPU policy, and artifact checks. Use the manual commands below only for advanced
recovery or debugging.

The Unsloth Core training pipeline transforms an NPC subject specification into a playable GGUF-quantized LoRA model ready for Unity deployment. The pipeline follows nine canonical stages tracked in the pipeline run manifest:

```
Subject Spec → [Preflight] → [Generate] → [Sanitize] → [Dataset Eval] → [Train] → [Export] → [Evaluate] → [Feedback]
```

> **Pipeline Manifest:** Each stage auto-records to `.pipeline/run_manifest.json` via `record_pipeline_stage()`.
>
> **Environment:** All pipeline scripts auto-load `.env.local` via `src/core/ops/env_loader.py` — no manual `export` needed.

---

## 1. Pipeline Stages

### Stage 0: Preflight

**Script:** `src/core/ops/preflight.py`

Runs before expensive pipeline stages to check the local environment and apply safe defaults:
- **GPU Memory Inventory**: Queries `nvidia-smi` for free and total VRAM in GiB
- **Auto-Downgrade**: If `fast-3b` is requested but VRAM < 10GB, downgrades to `safe-any`
- **Ollama Auto-Unload**: Detects and stops running Ollama models to free VRAM
- **GCC Toolchain**: Verifies `gcc` is available for Triton compilation
- **Confident AI**: Checks if `CONFIDENT_API_KEY` is configured
- Records preflight metadata (VRAM, GCC status, etc.) to the pipeline manifest

**CLI:** `./ucore audit check` or standalone `python src/core/ops/preflight.py --phase train --preset fast-3b`

---

### Stage 1: Generate Dataset

**Production entry point:** `./ucore generate-ollama <spec>`
**Script:** `src/core/dataset/generate_dataset_ollama.py`

**Legacy/smoke entry point:** `./ucore generate <spec>`
**Legacy script:** `src/core/dataset/generate_dataset.py`

Reads a subject spec JSON and produces a ChatML-format Q&A dataset.

**Production rule:** use `./ucore generate-ollama` for Ollama production data.
`./ucore generate --technique ollama` is legacy/fallback and should not be used for production.

**Technique selection for legacy `generate` (--technique):**

| Technique | Description | When to use |
|-----------|-------------|-------------|
| `template` | **Default.** Fast deterministic generation for pipeline testing. | Smoke tests and pipeline testing |
| `ollama` / `openai` / `anthropic` | LLM-driven synthetic data generation | Production-quality datasets using external LLMs |

**Output:** `data/datasets/{npc_key}/{technique}/train.jsonl`

**Onyx generation (v2):**
- Uses natural conversation templates with deterministic variant selection via `_pick_variant()` (hash-based)
- Variants per category: teaching (3), dialogue (3), identity (2), quest (2), refusal (2)
- Content cleaner strips markdown headings, bold markers, list prefixes
- Reference docs indexed at `data/npcs/reference_docs/` (centralized, per-NPC primer files)
- ~72 examples per NPC: 8 identity + 32 teaching + 16 dialogue + 8 quest + 8 refusal

**Key CLI flags:**
```bash
./ucore generate data/npcs/specs/history_guide.json
./ucore generate data/npcs/specs/history_guide.json --technique template
./ucore generate-ollama data/npcs/specs/history_guide.json --model qwen2.5:7b --fresh
./ucore generate data/npcs/specs/history_guide.json --technique template --push-to-confident  # Push dataset to Confident AI
```

*Records `generate` stage to pipeline manifest with train/validation paths.*

### Stage 2: Sanitize Dataset

**Entry point:** `./ucore sanitize <input>`
**Script:** `src/core/dataset/sanitize_dataset.py`

Validates dataset integrity:
- Confirms ChatML format (role/content turn structure)
- Strips leading/trailing whitespace on content fields
- Ensures no empty messages
- Outputs clean version

**Output:** `{input_path}_clean.jsonl` (in same directory as input)

*Records `sanitize` stage to pipeline manifest with output path.*

### Stage 2b: Dataset Quality Eval

**Entry point:** `./ucore dataset-eval <spec>`
**Script:** `src/core/dataset/dataset_eval.py`

Runs the committed DeepEval suite against the sanitized dataset before training.
This is the local build-loop gate for dataset generation quality, not a final
model validation step.

```bash
./ucore dataset-eval data/npcs/specs/history_guide.json \
  --technique template \
  --mode fast \
  --judge-model qwen2.5:7b \
  --cases-per-category 1
```

**Local defaults:**
- Judge: `qwen2.5:7b` via Ollama, temperature 0.
- Mode: `fast` by default, sampling 1 row per category. Use `--mode release` for the strict 5-row-per-category final check.
- Confident AI: auto-uploads results when `CONFIDENT_API_KEY` is configured. Use `--confident` to enforce API key presence (exits if missing).
- Dataset input: `data/datasets/{npc_key}/{technique}/train_clean.jsonl`.
- Test suite: `tests/evals/test_dataset_generation_quality.py`.

**Outputs:**
- `data/datasets/{npc_key}/{technique}/quality_summary.json`
- `data/datasets/{npc_key}/{technique}/quality_failures.json`

Use `quality_failures.json` as the source of truth for what to regenerate or
rewrite next. Do not lower metric thresholds or delete failing rows to make a
run pass.

**Quality gate enforcement:**
Training is **blocked by default** unless the quality gate has passed against
the exact sanitized dataset. In `train.py`, the
`dataset_quality_gate_errors()` function validates:

- The dataset is `train_clean.jsonl`, not raw `train.jsonl`
- `quality_summary.json` exists with `status: "ok"`
- Zero distribution gaps, zero unknown rows, clean sanitizer quality signals, and matching content hash
- Zero failing sampled DeepEval cases only when the summary was produced with `--mode release`; `fast` mode keeps sampled failures diagnostic so iteration can reach training sooner
- Content hash matches the hash recorded when the gate ran — any modification
  invalidates the gate

Pass `--allow-ungated-dataset` to `train.py` (`./ucore train`) to bypass
this check for development iteration. Production pipeline runs should never
skip the gate.

**Shared contract constants:**
The file `src/core/dataset/dataset_contracts.py` centralizes the contract data
used across generation, validation, and eval stages:

| Constant | Value |
|----------|-------|
| `SUPPORTED_DATASET_CATEGORIES` | `("identity", "teaching", "dialogue", "quest", "refusal")` |
| `MIN_DATASET_EXAMPLES_PER_CATEGORY` | `{"identity": 8, "teaching": 32, "dialogue": 16, "quest": 8, "refusal": 8}` |
| `VALID_DIFFICULTY_LEVELS` | `("beginner", "intermediate", "advanced")` |

It also provides helpers: `expected_examples_per_category()`,
`calculate_distribution_gaps()`, `summarize_jsonl_dataset()`, and
`dataset_contract_from_spec()`.

*Records `dataset_eval` stage to pipeline manifest with pass_rate, confident_url.*

### Stage 3: Training

**Entry point:** `./ucore train <spec>`
**Script:** `src/core/training/train.py`

Uses Unsloth's `SFTTrainer` with LoRA for parameter-efficient fine-tuning. Config hierarchy:

```
Base config → Preset override → CLI override
(etc/lora-sft-*.yaml)  (etc/presets/*.yaml)  (--flags)
```

**Preset selection:**

| Preset | Model | LoRA rank | Epochs | Batch | When to use |
|--------|-------|-----------|--------|-------|-------------|
| `smoke` | LLaMA 3.2 1B | 8 | 1 | 2 | Debugging/testing pipeline |
| `fast-3b` | LLaMA 3.2 3B | 16 | 5 | 4 | Standard NPC training |
| `safe-any` | Auto-detect | 8 | 3 | 2 | CUDA OOM fallback |
| `wandb` | (inherits) | --- | --- | --- | W&B experiment tracking (use as overlay) |

**Output:** `artifacts/models/{npc_key}/` (LoRA adapter weights)

**GPU:** RTX 3060 Laptop 6GB → `fast-3b` tuned with `packing: true`, `batch_size: 1`, `gradient_accumulation_steps: 8`.

**Checkpointing:**
- Intermediate checkpoints saved to `artifacts/models/{npc_key}/runs/{run_id}/`
- TensorBoard logs also in `artifacts/models/{npc_key}/runs/`

**Export flag:**
- `--export-gguf` exports adapter GGUF automatically after training (no separate export step needed)
- Output: `artifacts/exports/{npc_key}/{npc_key}-lora-f16.gguf`

*Records `train` stage to pipeline manifest with run_dir, output_dir, training_loss.*

### Stage 4: Export

**Entry point:** `./ucore export <npc_key>`
**Scripts:** `src/core/export/export.py`

**Adapter mode (default):**
- Converts LoRA adapter to lightweight f16 GGUF via `convert_lora_to_gguf.py`
- Fast, no base model loading (~30 seconds)
- Output: `artifacts/exports/{npc_key}/{npc_key}-lora-f16.gguf` (~47 MB)
- **This is what Unity/LLMUnity loads at runtime** (base model stays in StreamingAssets)

**Full-merge mode (`--full-merge`):**
- Merges LoRA into base model, then quantizes
- Output: `artifacts/exports/{npc_key}/{npc_key}-{model}-{quant}.gguf`
- Note: May timeout on HF safetensor download

*Records `export` stage to pipeline manifest with output_dir, gguf_files, mode.*

### Stage 5: Model Evaluation

**Entry point:** `./ucore evaluate <args>`
**Scripts:** `src/core/evaluation/evaluate.py`

Compares two models (baseline vs candidate) or measures standalone:

```bash
# Side-by-side comparison
./ucore evaluate \
  --baseline artifacts/exports/history_guide/round1/history_guide-lora-f16.gguf \
  --candidate artifacts/exports/history_guide/history_guide-lora-f16.gguf \
  --base-model /path/to/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec data/npcs/specs/history_guide.json \
  --report-html \
  --feedback-json artifacts/eval/results/feedback/history_guide_round2.json

# Standalone measurement (no comparison)
./ucore evaluate --baseline artifacts/exports/history_guide/history_guide-lora-f16.gguf \
  --spec data/npcs/specs/history_guide.json --report-html
```

**Key details:**
- Starts two `llama-server` instances (baseline on 8888, candidate on 8889) with `--lora`
- Both baseline and candidate can be LoRA adapters loaded on top of `--base-model`
- Same mechanism as LLMUnity runtime: base GGUF + LoRA via llama.cpp
- Validates responses on: sentence count ≤ max, name mention, AI disclaimers, think tags
- Quality metrics: lexical diversity (TTR), repetition rate, response length
- Optional Ollama LLM judge for semantic comparison (falls back to heuristic)

**Output:**
- HTML report with Chart.js (bar chart + scatter plot)
- Markdown per-question breakdown
- Structured feedback JSON with per-concept win rates, quality scores, constraint violations

*Records `evaluate` stage to pipeline manifest with candidate/baseline paths. Use `--deepeval` to also run DeepEval model quality evaluation and push results to Confident AI.*

### Stage 6: Feedback Loop

**Entry point:** `./ucore feedback <feedback.json>`
**Scripts:** `src/core/training/feedback_loop.py`, `src/core/evaluation/evaluate.py --feedback-json`

Closes the loop between evaluation and dataset generation:

1. Analyze feedback JSON → identify weak concepts (win_rate < 0.5, quality > 25, violations > 1)
2. Query Onyx for each weak concept → determine gap type:
   - **training_density**: Onyx has relevant docs → regenerate more examples
   - **knowledge_gap**: Onyx returns nothing → add reference doc, re-index
3. Regenerate targeted dataset → sanitize → dataset-eval → retrain → re-evaluate
4. Control the pre-training gate with:
   - `--skip-dataset-eval` to bypass the quality gate before training
   - `--deepeval-judge-model` to select the Ollama judge model
   - `--deepeval-ollama-url` to point at a custom local Ollama server
   - `--deepeval-cases-per-category` to adjust evaluation depth
   - `--deepeval-soft-fail` to write DeepEval artifacts but continue training even if the gate fails
5. CI mode: `--auto-retrain` chains the whole cycle in one command

---

## Environment Auto-Configuration

The `src/core/ops/env_loader.py` module auto-sources `.env.local` on import across all pipeline scripts. This means:
- `CONFIDENT_API_KEY` is automatically loaded from `.env.local` — no manual `export` needed
- All pipeline scripts get consistent environment without individual setup
- Idempotent: only loads once per process

---

## 8. Preflight System

The preflight system (`src/core/ops/preflight.py`) runs before expensive pipeline
stages (training, dataset-eval) to check the local environment and apply safe
defaults.

### Checks Performed

1. **GPU Memory Inventory**: Queries `nvidia-smi` for free and total VRAM in GiB.
2. **Auto-Downgrade**: If `--preset fast-3b` is requested but total VRAM is
   below 10 GB, automatically downgrades to `safe-any` (the
   `DEFAULT_FALLBACK_PRESET`).
3. **Ollama Auto-Unload**: Detects running Ollama models and stops them to free
   VRAM (can be disabled with `--no-auto-unload-ollama`).
4. **GCC Toolchain Check**: Verifies `gcc` is available in PATH before training
   (required for Triton compilation).

### PreflightReport

Returned as a `PreflightReport` dataclass with:
- `status`: `"ok"`, `"degraded"` (warnings), or `"blocked"` (errors)
- `preset_requested` / `preset_effective`: What was asked for vs. what will run
- `total_vram_gb` / `free_vram_gb`: GPU memory snapshot
- `gcc_ok` / `gcc_path`: GCC availability
- `running_ollama_models` / `stopped_ollama_models`: Ollama state changes
- `recommendation`: Structured training location advice (local vs. remote Colab)

### CLI Usage

```bash
# Standalone preflight check
python src/core/ops/preflight.py --phase train --preset fast-3b --spec data/npcs/specs/history_guide.json

# JSON output for programmatic use
python src/core/ops/preflight.py --phase train --preset fast-3b --json

# Skip Ollama unload or GCC check
python src/core/ops/preflight.py --phase train --no-auto-unload-ollama --no-gcc-check
```

---

## 9. Ollama Model Presets

Ollama model presets provide named aliases for generation and judging models,
resolved from `etc/ollama-model-presets.yaml`. Explicit CLI model names
always win over presets.

### Preset File

```yaml
# etc/ollama-model-presets.yaml
default_generation: generate-qwen25
default_judge: judge-qwen25

generation:
  generate-qwen25: qwen2.5:7b
  generate-llama31: llama3.1:8b

judge:
  judge-qwen25: qwen2.5:7b
  judge-llama31-exp: llama3.1:8b
```

### Resolution Logic

`src/core/ops/ollama_model_presets.py` resolves the effective model via
`resolve_ollama_model()` with this priority:

1. **Explicit CLI model** — `--model qwen2.5:7b` wins unconditionally
2. **Explicit CLI preset** — `--preset judge-qwen25` maps through the preset
   file
3. **Role-specific default preset** — `default_generation` / `default_judge`
   from YAML
4. **Safety fallback** — `qwen2.5:7b` for judge and generation

### Generation Presets

| Preset Name | Model | Use Case |
|-------------|-------|----------|
| `generate-qwen25` | `qwen2.5:7b` | Default generation (balanced speed/quality) |
| `generate-llama31` | `llama3.1:8b` | Alternative generation model |

### Judge Presets

| Preset Name | Model | Use Case |
|-------------|-------|----------|
| `judge-qwen25` | `qwen2.5:7b` | **Default local judge** (dataset-eval) |
| `judge-llama31-exp` | `llama3.1:8b` | Experimental judge |

### Default Judge

The local default judge for dataset-eval is `judge-qwen25` → `qwen2.5:7b`.
This is configured at three levels (in priority order):

1. CLI flag: `--judge-model qwen2.5:7b`
2. Env var: `DEEPEVAL_OLLAMA_MODEL` (injected by `dataset_eval.py`)
3. Code default: YAML `default_judge` → `judge-qwen25` → `qwen2.5:7b`
   in `ollama_model_presets.py`

---

## 10. Subject Spec Format

Located in `data/npcs/specs/*.json`. Structure (using history_guide as example):

```json
{
  "npc_key": "history_guide",
  "npc_name": "HistoryGuide",
  "identity": {
    "personality": "Patient, enthusiastic storyteller who brings historical events to life",
    "background": "Expert in world history with focus on ancient civilizations",
    "mannerisms": "Uses timelines and cause-effect reasoning; connects past to present"
  },
  "teaching": {
    "expertise": ["ancient civilizations", "Roman Empire", "medieval period", "world wars"],
    "approach": "Connects events through narrative storytelling",
    "difficulty_levels": ["beginner", "intermediate"]
  },
  "dialogue": {
    "conversation_style": "Narrative and engaging with clear chronological framing",
    "max_sentences": 3,
    "example_topics": ["What caused the fall of Rome?", "Tell me about daily life in ancient Egypt"]
  },
  "quest": {
    "scenarios": [
      {"name": "timeline_analysis", "description": "Student needs cause-effect relationships"}
    ]
  },
  "refusal": {
    "boundaries": ["Will not promote historical misinformation or conspiracy theories"],
    "redirect_policy": "Redirects to verified historical sources and scholarly consensus"
  },
  "subject": "World history: ancient civilizations, classical antiquity, medieval period...",
  "reference_doc": "data/npcs/reference_docs/history_primer.md",
  "system_prompt": "## IDENTITY\nName: HistoryGuide | Role: engaging world history storyteller\n\n## VOICE\n...\n\n## KNOWLEDGE\nAncient civilizations, Roman Empire, medieval period...\n\n## RULES\nNEVER speculate without labeling | NEVER promote misinformation...",
  "research_queries": [
    {"query": "key events and causes of the fall of the Roman Empire", "mode": "fast"},
    {"query": "daily life in ancient Egypt explained simply", "mode": "fast"}
  ],
  "dataset": {
    "examples_per_category": {
      "identity": 8,
      "teaching": 32,
      "dialogue": 16,
      "quest": 8,
      "refusal": 8
    }
  }
}
```

**Key fields:**
- `reference_doc`: Path to the primer file in `data/npcs/reference_docs/` — used for Onyx indexing
- `system_prompt`: 4-section IDENTITY|VOICE|KNOWLEDGE|RULES format for LLMUnity compatibility
- `examples_per_category`: Onyx-optimized distribution (72 total)
- `research_queries`: Domain-specific queries used for Onyx coverage checking (no `from: "web"` needed)

**Conventions:**
- `npc_key` always `snake_case`
- GGUF naming: `{npc_key}-lora-f16.gguf` (adapter) or `{npc_key}-{model}-{quant}.gguf` (full-merge)
- Default quantization: `q4_k_m` for full-merge, `f16` for adapter mode

---

## 11. Quick Commands

```bash
# 1. Activate
source unsloth_env/bin/activate

# 2. Scaffold a new NPC
./ucore init new_npc --subject "Topic description"

# 3. Generate a docs-backed dataset
./ucore generate data/npcs/specs/new_npc.json --technique docs --docs-manifest path/to/curated_corpus.jsonl

# 4. Quick smoke test
./ucore pipeline data/npcs/specs/new_npc.json --preset smoke

# 5. Full production pipeline
./ucore generate data/npcs/specs/new_npc.json --technique docs --docs-manifest path/to/curated_corpus.jsonl
./ucore sanitize data/datasets/new_npc/docs/train.jsonl
./ucore train data/npcs/specs/new_npc.json --technique docs --preset fast-3b --export-gguf
./ucore evaluate --baseline artifacts/exports/new_npc/new_npc-lora-f16.gguf \
  --spec data/npcs/specs/new_npc.json --report-html

# 6. W&B tracking
./ucore train data/npcs/specs/new_npc.json --technique docs --preset fast-3b --wandb --export-gguf

# 7. Compare two rounds
./ucore evaluate \
  --baseline artifacts/exports/new_npc/round1/new_npc-lora-f16.gguf \
  --candidate artifacts/exports/new_npc/new_npc-lora-f16.gguf \
  --base-model Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec data/npcs/specs/new_npc.json --report-html

# 8. Feedback loop
./ucore feedback artifacts/eval/results/feedback/new_npc_round2.json --dry-run
```

---

## 12. Output Artifacts

| Stage | Output Path | Format |
|-------|-------------|--------|
| Generate | `data/datasets/{npc_key}/{technique}/train.jsonl` | JSONL (ChatML) |
| Sanitize | `data/datasets/{npc_key}/{technique}/train_clean.jsonl` | JSONL (cleaned) |
| Train | `artifacts/models/{npc_key}/runs/{run_id}/` | LoRA adapter (SafeTensors) |
| Export | `artifacts/exports/{npc_key}/{npc_key}-lora-f16.gguf` | GGUF (adapter) |
| Evaluate | `artifacts/eval/reports/{npc_key}/eval_*.html` | HTML (Chart.js) |
| Evaluate | `artifacts/eval/results/feedback/{npc_key}_*.json` | JSON (per-concept) |
| Feedback | `artifacts/eval/results/gaps/{npc_key}.json` | JSON (gap analysis) |

---

## 13. Data Flow Diagram

```
data/npcs/specs/{npc_key}.json ──── data/npcs/reference_docs/{npc_key}_primer.md
          │
          ▼
  ./ucore generate data/npcs/specs/{npc_key}.json --technique docs --docs-manifest path/to/curated_corpus.jsonl ──► Docs retrieval/manifest prep
          │
          ▼
  src/core/dataset/generate_dataset.py ──► Docs retrieval
          │
          ▼
  data/datasets/{npc_key}/docs/train.jsonl
          │
          ▼
  src/core/dataset/sanitize_dataset.py ──► train_clean.jsonl
          │
          ▼
  src/core/training/train.py ──► etc/*.yaml + etc/presets/*.yaml
          │
          ▼
  artifacts/models/{npc_key}/runs/{run_id}/  (LoRA adapter)
          │
          ▼
  src/core/export/export.py ──► artifacts/exports/{npc_key}/{npc_key}-lora-f16.gguf
          │
          ▼
  src/core/evaluation/evaluate.py ──► artifacts/eval/reports/ + artifacts/eval/results/feedback/
          │
          ▼
  Unity StreamingAssets/Models/{npc_key}-lora-f16.gguf
```

---

## 14. Config Hierarchy

Training configs are intentionally simple now:

1. **Spec-derived base**: `src/core/training/train.py` builds the effective config from `data/npcs/specs/{npc}.json`, the detected canonical dataset path, and the default Llama 3.2 3B model.
2. **Preset** (`etc/presets/{name}.yaml`) overrides hyperparameters. Current active presets are `fast-3b`, `safe-any`, `smoke`.
3. **CLI flags** (`--lr`, `--epochs`, `--wandb`, etc.) override everything above.

Use one training preset plus `--wandb` as a flag:
```bash
./ucore train data/npcs/specs/history_guide.json --preset fast-3b --wandb --export-gguf
```

`etc/lora-sft-base.yaml` remains as the canonical base config for validation/planning tools (`validate_config.py`, `plan_execution.py`). Duplicate top-level model configs and old Qwen/0.5B/1B presets were removed to avoid drift.

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

## 15. Docs Integration

Docs is the grounded generation path. The pipeline uses it to:

**During generation:**
- Retrieve relevant context chunks from the curated corpus manifest
- Feed context to deterministic template for grounded Q&A generation
- Support document-set scoping per NPC
- Natural conversation templates (v2) with hash-based variant selection

**Docs-backed generation:**
```bash
./ucore generate data/npcs/specs/history_guide.json \
  --technique docs \
  --docs-manifest path/to/curated_corpus.jsonl
```

---

## 16. Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview and quick start |
| `AGENTS.md` | AI agent reference (architecture, commands, logic map) |
| `docs/training-workflow.md` | This document — full pipeline detail |
| `docs/legacy-cli-reference.md` | Docs flags, generation, and dataset workflow |
| `data/npcs/specs/*.json` | NPC specification files |
| `etc/*.yaml` | Training configuration base files |
| `etc/presets/*.yaml` | Training presets (hyperparameter profiles) |
