# Unsloth Core Training Workflow

## Overview

The Unsloth Core training pipeline transforms an NPC subject specification into a playable GGUF-quantized LoRA model ready for Unity deployment. The pipeline follows six stages:

```
Subject Spec (JSON) → [Generate] → [Sanitize] → [Train] → [Export] → [Evaluate] → GGUF
                                                                           ↓
                                                              [Feedback Loop] —→ retrain
```

---

## 1. Pipeline Stages

### Stage 1: Generate Dataset

**Entry point:** `./ucore generate <spec>`
**Script:** `scripts/generate_dataset.py`

Reads a subject spec JSON and produces a ChatML-format Q&A dataset.

**Technique selection (--technique):**

| Technique | Description | When to use |
|-----------|-------------|-------------|
| `template` | **Default.** Fast deterministic generation for pipeline testing. | Smoke tests and pipeline testing |
| `ollama` / `openai` / `anthropic` | LLM-driven synthetic data generation | Production-quality datasets using external LLMs |

**Output:** `subjects/datasets/{npc_key}/{technique}/train.jsonl`

**Onyx generation (v2):**
- Uses natural conversation templates with deterministic variant selection via `_pick_variant()` (hash-based)
- Variants per category: teaching (3), dialogue (3), identity (2), quest (2), refusal (2)
- Content cleaner strips markdown headings, bold markers, list prefixes
- Reference docs indexed at `subjects/reference_docs/` (centralized, per-NPC primer files)
- ~72 examples per NPC: 8 identity + 32 teaching + 16 dialogue + 8 quest + 8 refusal

**Key CLI flags:**
```bash
./ucore generate subjects/history_guide.json
./ucore generate subjects/history_guide.json --technique template
./ucore generate subjects/history_guide.json --technique ollama --model llama3.1
```

### Stage 2: Sanitize Dataset

**Entry point:** `./ucore sanitize <input>`
**Script:** `scripts/sanitize_dataset.py`

Validates dataset integrity:
- Confirms ChatML format (role/content turn structure)
- Strips leading/trailing whitespace on content fields
- Ensures no empty messages
- Outputs clean version

**Output:** `{input_path}_clean.jsonl` (in same directory as input)

### Stage 3: Dataset Quality Eval

**Entry point:** `./ucore dataset-eval <spec>`
**Script:** `scripts/dataset_eval.py`

Runs the committed DeepEval suite against the sanitized dataset before training.
This is the local build-loop gate for dataset generation quality, not a final
model validation step.

```bash
./ucore dataset-eval subjects/history_guide.json \
  --technique template \
  --judge-model qwen2.5:7b \
  --cases-per-category 1
```

**Local defaults:**
- Judge: `qwen2.5:7b` via Ollama, temperature 0.
- Confident AI: disabled by default.
- Dataset input: `subjects/datasets/{npc_key}/{technique}/train_clean.jsonl`.
- Test suite: `tests/evals/test_dataset_generation_quality.py`.

**Outputs:**
- `subjects/datasets/{npc_key}/{technique}/quality_summary.json`
- `subjects/datasets/{npc_key}/{technique}/quality_failures.json`

Use `quality_failures.json` as the source of truth for what to regenerate or
rewrite next. Do not lower metric thresholds or delete failing rows to make a
run pass.

### Stage 4: Training

**Entry point:** `./ucore train <spec>`
**Script:** `scripts/train.py`

Uses Unsloth's `SFTTrainer` with LoRA for parameter-efficient fine-tuning. Config hierarchy:

```
Base config → Preset override → CLI override
(configs/lora-sft-*.yaml)  (configs/presets/*.yaml)  (--flags)
```

**Preset selection:**

| Preset | Model | LoRA rank | Epochs | Batch | When to use |
|--------|-------|-----------|--------|-------|-------------|
| `smoke` | LLaMA 3.2 1B | 8 | 1 | 2 | Debugging/testing pipeline |
| `fast-3b` | LLaMA 3.2 3B | 16 | 5 | 4 | Standard NPC training |
| `safe-any` | Auto-detect | 8 | 3 | 2 | CUDA OOM fallback |
| `wandb` | (inherits) | — | — | — | W&B experiment tracking (use as overlay) |

**Output:** `outputs/{npc_key}/` (LoRA adapter weights)

**GPU:** RTX 3060 Laptop 6GB → `fast-3b` tuned with `packing: true`, `batch_size: 1`, `gradient_accumulation_steps: 8`.

**Checkpointing:**
- Intermediate checkpoints saved to `outputs/{npc_key}/runs/{run_id}/`
- TensorBoard logs also in `outputs/{npc_key}/runs/`

**Export flag:**
- `--export-gguf` exports adapter GGUF automatically after training (no separate export step needed)
- Output: `exports/{npc_key}/{npc_key}-lora-f16.gguf`

### Stage 5: Export

**Entry point:** `./ucore export <npc_key>`
**Scripts:** `scripts/export.py`

**Adapter mode (default):**
- Converts LoRA adapter to lightweight f16 GGUF via `convert_lora_to_gguf.py`
- Fast, no base model loading (~30 seconds)
- Output: `exports/{npc_key}/{npc_key}-lora-f16.gguf` (~47 MB)
- **This is what Unity/LLMUnity loads at runtime** (base model stays in StreamingAssets)

**Full-merge mode (`--full-merge`):**
- Merges LoRA into base model, then quantizes
- Output: `exports/{npc_key}/{npc_key}-{model}-{quant}.gguf`
- Note: May timeout on HF safetensor download

### Stage 6: Model Evaluation

**Entry point:** `./ucore evaluate <args>`
**Scripts:** `scripts/evaluate.py`

Compares two models (baseline vs candidate) or measures standalone:

```bash
# Side-by-side comparison
./ucore evaluate \
  --baseline exports/history_guide/round1/history_guide-lora-f16.gguf \
  --candidate exports/history_guide/history_guide-lora-f16.gguf \
  --base-model /path/to/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec subjects/history_guide.json \
  --report-html \
  --feedback-json eval/results/feedback/history_guide_round2.json

# Standalone measurement (no comparison)
./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf \
  --spec subjects/history_guide.json --report-html
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

### Stage 7: Feedback Loop

**Entry point:** `./ucore feedback <feedback.json>`
**Scripts:** `scripts/feedback_loop.py`, `scripts/evaluate.py --feedback-json`

Closes the loop between evaluation and dataset generation:

1. Analyze feedback JSON → identify weak concepts (win_rate < 0.5, quality > 25, violations > 1)
2. Query Onyx for each weak concept → determine gap type:
   - **training_density**: Onyx has relevant docs → regenerate more examples
   - **knowledge_gap**: Onyx returns nothing → add reference doc, re-index
3. Regenerate targeted dataset → sanitize → dataset-eval → retrain → re-evaluate
4. CI mode: `--auto-retrain` chains the whole cycle in one command

---

## 2. Subject Spec Format

Located in `subjects/*.json`. Structure (using history_guide as example):

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
  "reference_doc": "subjects/reference_docs/history_primer.md",
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
- `reference_doc`: Path to the primer file in `subjects/reference_docs/` — used for Onyx indexing
- `system_prompt`: 4-section IDENTITY|VOICE|KNOWLEDGE|RULES format for LLMUnity compatibility
- `examples_per_category`: Onyx-optimized distribution (72 total)
- `research_queries`: Domain-specific queries used for Onyx coverage checking (no `from: "web"` needed)

**Conventions:**
- `npc_key` always `snake_case`
- GGUF naming: `{npc_key}-lora-f16.gguf` (adapter) or `{npc_key}-{model}-{quant}.gguf` (full-merge)
- Default quantization: `q4_k_m` for full-merge, `f16` for adapter mode

---

## 3. Quick Commands

```bash
# 1. Activate
source unsloth_env/bin/activate

# 2. Scaffold a new NPC
./ucore init new_npc --subject "Topic description"

# 3. Index reference docs into Onyx
python scripts/onyx_index_repo.py --npc-key new_npc \
  --glob subjects/new_npc.json \
  --glob subjects/reference_docs/new_npc_primer.md

# 4. Quick smoke test
./ucore pipeline subjects/new_npc.json --preset smoke

# 5. Full production pipeline
./ucore generate subjects/new_npc.json --technique onyx
./ucore sanitize subjects/datasets/new_npc/onyx/train.jsonl
./ucore train subjects/new_npc.json --technique onyx --preset fast-3b --export-gguf
./ucore evaluate --baseline exports/new_npc/new_npc-lora-f16.gguf \
  --spec subjects/new_npc.json --report-html

# 6. W&B tracking
./ucore train subjects/new_npc.json --technique onyx --preset fast-3b --wandb --export-gguf

# 7. Compare two rounds
./ucore evaluate \
  --baseline exports/new_npc/round1/new_npc-lora-f16.gguf \
  --candidate exports/new_npc/new_npc-lora-f16.gguf \
  --base-model Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec subjects/new_npc.json --report-html

# 8. Feedback loop
./ucore feedback eval/results/feedback/new_npc_round2.json --dry-run
```

---

## 4. Output Artifacts

| Stage | Output Path | Format |
|-------|-------------|--------|
| Generate | `subjects/datasets/{npc_key}/{technique}/train.jsonl` | JSONL (ChatML) |
| Sanitize | `subjects/datasets/{npc_key}/{technique}/train_clean.jsonl` | JSONL (cleaned) |
| Train | `outputs/{npc_key}/runs/{run_id}/` | LoRA adapter (SafeTensors) |
| Export | `exports/{npc_key}/{npc_key}-lora-f16.gguf` | GGUF (adapter) |
| Evaluate | `eval/reports/{npc_key}/eval_*.html` | HTML (Chart.js) |
| Evaluate | `eval/results/feedback/{npc_key}_*.json` | JSON (per-concept) |
| Feedback | `eval/results/gaps/{npc_key}.json` | JSON (gap analysis) |

---

## 5. Data Flow Diagram

```
subjects/{npc_key}.json ──── subjects/reference_docs/{npc_key}_primer.md
          │
          ▼
  scripts/onyx_index_repo.py ──► Onyx (vector DB)
          │
          ▼
  scripts/generate_dataset.py ──► Onyx retrieval
          │
          ▼
  subjects/datasets/{npc_key}/onyx/train.jsonl
          │
          ▼
  scripts/sanitize_dataset.py ──► train_clean.jsonl
          │
          ▼
  scripts/train.py ──► configs/*.yaml + presets/*.yaml
          │
          ▼
  outputs/{npc_key}/runs/{run_id}/  (LoRA adapter)
          │
          ▼
  scripts/export.py ──► exports/{npc_key}/{npc_key}-lora-f16.gguf
          │
          ▼
  scripts/evaluate.py ──► eval/reports/ + eval/results/feedback/
          │
          ▼
  Unity StreamingAssets/Models/{npc_key}-lora-f16.gguf
```

---

## 6. Config Hierarchy

Training configs are intentionally simple now:

1. **Spec-derived base**: `scripts/train.py` builds the effective config from `subjects/{npc}.json`, the detected canonical dataset path, and the default Llama 3.2 3B model.
2. **Preset** (`configs/presets/{name}.yaml`) overrides hyperparameters. Current active presets are `fast-3b`, `safe-any`, `smoke`, and `wandb`.
3. **CLI flags** (`--lr`, `--epochs`, `--wandb`, etc.) override everything above.

Use one training preset plus `--wandb` as a flag:
```bash
./ucore train subjects/history_guide.json --preset fast-3b --wandb --export-gguf
```

`configs/lora-sft-base.yaml` remains as the canonical base config for validation/planning tools (`validate_config.py`, `plan_execution.py`). Duplicate top-level model configs and old Qwen/0.5B/1B presets were removed to avoid drift.

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

## 7. Onyx Integration

Onyx is a local RAG knowledge base. The pipeline uses it to:

**During generation:**
- Retrieve relevant context chunks from indexed reference docs
- Feed context to deterministic template for grounded Q&A generation
- Support document-set scoping per NPC
- Natural conversation templates (v2) with hash-based variant selection

**Indexing reference docs:**
```bash
python scripts/onyx_index_repo.py     # index project-wide
python scripts/onyx_index_repo.py --npc-key history_guide \
  --glob subjects/history_guide.json \
  --glob subjects/reference_docs/history_primer.md
python scripts/onyx_index_repo.py --dry-run  # preview
```

**Onyx-backed generation:**
```bash
./ucore generate subjects/history_guide.json \
  --technique onyx \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200 \
  --onyx-prep
```

---

## 8. Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Project overview and quick start |
| `AGENTS.md` | AI agent reference (architecture, commands, logic map) |
| `docs/TRAINING_WORKFLOW_CONTEXT.md` | This document — full pipeline detail |
| `docs/ONYX_WORKFLOW.md` | Onyx setup, indexing, and generation workflow |
| `subjects/*.json` | NPC specification files |
| `configs/*.yaml` | Training configuration base files |
| `configs/presets/*.yaml` | Training presets (hyperparameter profiles) |
