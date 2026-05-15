# Unsloth Core Training Workflow

## Overview

The Unsloth Core training pipeline transforms an NPC subject specification into a playable GGUF-quantized LoRA model ready for Unity deployment. The pipeline follows four deterministic stages:

```
Subject Spec (JSON) → [Generate] → [Sanitize] → [Train] → [Export & Validate] → GGUF
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
| `onyx` | Default. Retrieves relevant context from local Onyx knowledge base, then generates Q&A via Ollama or direct prompt | Production: when Onyx is indexed with docs from the subject domain |
| `docs` | Reads a manifest of local markdown/text files and generates from those | Docs are available but not in Onyx |
| `ollama` | Uses Ollama to generate from model knowledge (no RAG context) | Quick prototyping |
| `template` | Simple template-based generation (smoke test only - NOT production) | Testing pipeline mechanics only |
| `openai` / `anthropic` | Uses OpenAI/Anthropic API to generate | Higher quality, costs money |

**Output:** `subjects/datasets/{npc_key}/{technique}/train.jsonl`

**Important constraints:**
- Onyx technique: chunk limit 10-12, 10s+ delays between calls (15-20 asks then rate block)
- Template technique is for smoke-test only; never train a production LoRA on template data

**Key CLI flags:**
```bash
./ucore generate subjects/chemistry_instructor.json
./ucore generate subjects/chemistry_instructor.json --technique onyx
./ucore generate subjects/chemistry_instructor.json --technique onyx --onyx-prep
./ucore generate subjects/chemistry_instructor.json --technique ollama --model llama3.1
./ucore generate subjects/chemistry_instructor.json --technique docs --docs-manifest docs/manifests/chemistry.json
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

### Stage 3: Training

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

**Running locally vs remotely:**
Before a long training run:
```bash
./ucore plan-execution --spec subjects/chemistry_instructor.json --preset fast-3b
```
This checks GPU VRAM, model size, and recommends local or Colab-based training.

**Training config files:**
- `configs/lora-sft-fast-3b.yaml` — Base 3B model config
- `configs/lora-sft-smoke.yaml` — Base 1B smoke config
- `configs/presets/fast-3b.yaml` — Training hyperparameter preset
- `configs/presets/smoke.yaml` — Smoke-test preset
- `configs/presets/safe-any.yaml` — Conservative fallback preset
- `configs/presets/wandb.yaml` — W&B tracking preset (--wandb alias)

**Checkpointing:**
- Intermediate checkpoints saved to `outputs/{npc_key}/runs/`
- TensorBoard logs also in `outputs/{npc_key}/runs/`

### Stage 4: Export & Validate

**Entry point:** `./ucore export <lora_path> --base-model <model>`
**Scripts:** `scripts/export.py`, `scripts/smoke_test.py`

**Export (scripts/export.py):**
- Merges LoRA adapter with base model
- Quantizes to GGUF format (default: q4_k_m)
- Output: `exports/{npc_key}-{model_short}-{quant}.gguf`

**Smoke test (scripts/smoke_test.py):**
- Loads exported GGUF
- Runs persona-adherence prompts from the subject spec
- Validates output quality and identity preservation
- Generates a report at `eval/results/{npc_key}/`

---

## 2. Subject Spec Format

Located in `subjects/*.json`. Structure:

```json
{
  "npc_key": "chemistry_instructor",          // snake_case key for the NPC
  "npc_name": "ChemistryInstructor",           // Display name
  "identity": {
    "personality": "Friendly, patient...",     // Personality description
    "backstory": "...",                        // NPC background
    "role": "high school chemistry teacher"    // Role definition
  },
  "teaching": {
    "subjects": ["stoichiometry", "periodic table", ...],
    "style": "Socratic",                       // Teaching approach
    "difficulty_level": "high_school",
    "max_explanations": 3,
    "use_analogies": true
  },
  "knowledge_sources": [                       // Reference sources for generation
    {"name": "...", "path": "docs/..."}
  ],
  "generation": {
    "num_examples": 100,                       // Target dataset size
    "max_turns": 6,                            // Max dialog turns per example
    "language": "en"
  },
  "evaluation_criteria": {
    "persona_accuracy": 0.85,                  // Minimum persona adherence
    "knowledge_correctness": 0.90              // Minimum factual accuracy
  }
}
```

**Conventions:**
- `npc_key` always `snake_case`
- GGUF naming: `{npc_key}-{model_short}-{quant}.gguf`
- Default quantization: `q4_k_m`

---

## 3. Quick Commands

```bash
# 1. Activate
source unsloth_env/bin/activate

# 2. Quick smoke test of the whole pipeline
./ucore pipeline subjects/chemistry_instructor.json --preset smoke

# 3. Full production pipeline
./ucore generate subjects/chemistry_instructor.json --technique onyx
./ucore sanitize subjects/datasets/chemistry_instructor/onyx/train.jsonl
./ucore train subjects/chemistry_instructor.json --preset fast-3b
./ucore export outputs/chemistry_instructor/lora_model --base-model llama3.2-3b
./ucore smoke exports/chemistry_instructor-llama3.2-3b-q4_k_m.gguf --spec subjects/chemistry_instructor.json

# 4. W&B tracking
./ucore train subjects/chemistry_instructor.json --preset wandb --preset fast-3b

# 5. Onyx-enabled generation with prep (index repo docs first)
./ucore generate subjects/chemistry_instructor.json --technique onyx --onyx-prep
```

---

## 4. Output Artifacts

| Stage | Output Path | Format |
|-------|-------------|--------|
| Generate | `subjects/datasets/{npc_key}/{technique}/train.jsonl` | JSONL (ChatML) |
| Sanitize | `subjects/datasets/{npc_key}/{technique}/train_clean.jsonl` | JSONL (cleaned) |
| Train | `outputs/{npc_key}/` | LoRA adapter (SafeTensors) |
| Export | `exports/{npc_key}-{model}-{quant}.gguf` | GGUF (quantized) |
| Validate | `eval/results/{npc_key}/` | HTML/MD report |

---

## 5. Data Flow Diagram

```
subjects/chemistry_instructor.json
          │
          ▼
  scripts/generate_dataset.py ───────► Onyx (local RAG)
          │                                │
          ▼                                ▼
  subjects/datasets/chemistry_instructor/     docs/ (indexed source)
          │
          ▼
  scripts/sanitize_dataset.py ─────► train_clean.jsonl
          │
          ▼
  scripts/train.py ─────► configs/lora-sft-*.yaml
          │                    └─ presets/*.yaml
          ▼
  outputs/chemistry_instructor/ (LoRA adapter)
          │
          ▼
  scripts/export.py ─────► exports/chemistry_instructor-*.gguf
          │
          ▼
  scripts/smoke_test.py ──► eval/results/chemistry_instructor/
          │
          ▼
  Unity StreamingAssets/Models/
```

---

## 6. Config Hierarchy

Training configs use a layered merge:

1. **Base config** (`configs/lora-sft-{model}.yaml`) defines model, dataset path template, LoRA hyperparams
2. **Preset** (`configs/presets/{name}.yaml`) overrides training-specific settings (epochs, LR, batch size)
3. **CLI flags** (`--lr`, `--epochs`, etc.) override everything above

Multiple presets can be stacked:
```bash
./ucore train subjects/chemistry_instructor.json \
  --preset fast-3b \
  --preset wandb
```

Example preset (`fast-3b.yaml`):
```yaml
model_name: "unsloth/Llama-3.2-3B-Instruct"
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
per_device_train_batch_size: 4
gradient_accumulation_steps: 4
learning_rate: 2e-4
num_train_epochs: 5
max_seq_length: 2048
warmup_steps: 10
logging_steps: 1
save_steps: 50
```

---

## 7. Onyx Integration

Onyx is a local RAG knowledge base. The pipeline uses it to:

**During generation:**
- Retrieve relevant context chunks from indexed docs
- Feed context to LLM for accurate Q&A generation
- Support document-set scoping per subject

**Configuration:**
```bash
# .env
ONYX_BASE_URL=http://localhost
ONYX_API_KEY=onyx_pat_...
```

**Indexing repo content:**
```bash
python scripts/onyx_index_repo.py     # index project docs/specs/configs
python scripts/onyx_index_repo.py --dry-run  # preview without indexing
```

**Onyx-backed generation:**
```bash
./ucore generate subjects/chemistry_instructor.json \
  --technique onyx \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200 \
  --onyx-prep
```

The `--onyx-prep` flag indexes targeted subject context and checks coverage before generation.

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
