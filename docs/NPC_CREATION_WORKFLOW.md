# NPC Creation Workflow

This guide walks you through creating a complete NPC end-to-end using the dashboard or CLI. It covers subject specs, dataset generation, training, and export.

## Overview: 5-Step Pipeline

1. **Create Subject Spec** — Define NPC identity, teaching style, and generation config
2. **Generate Dataset** — Use Onyx/Ollama/NotebookLM to create training data
3. **Sanitize Dataset** — Validate ChatML format, remove duplicates, clean whitespace
4. **Train LoRA Adapter** — Fine-tune a base model (gemma, llama2, etc.) using Unsloth
5. **Export to GGUF** — Quantize and convert for Unity/LLMUnity deployment

---

## Step 1: Create Subject Spec

A **subject spec** is a JSON file that defines everything about your NPC.

**Location**: `subjects/<npc_key>.json`

**Minimal Template**:
```json
{
  "npc_key": "my_npc",
  "name": "My NPC Name",
  "identity": "Short persona/role description. Who are they?",
  "llm": {
    "model_name": "gemma4:e2b"
  },
  "generation": {
    "prompts": {
      "seed": "Example prompt or teaching direction"
    }
  },
  "training": {
    "preferred_preset": "fast-3b"
  },
  "metadata": {
    "author": "your_name",
    "tags": ["category", "type"]
  }
}
```

**Key Fields**:
- **npc_key**: snake_case identifier (no spaces, no special chars except `_`)
- **name**: Human-readable display name
- **identity**: 1–3 sentences describing the NPC's role and teaching style
- **llm.model_name**: Base LLM (e.g., `gemma4:e2b`, `llama2`, `mistral`)
- **generation.prompts.seed**: Example Q&A seed or teaching direction
- **training.preferred_preset**: `smoke`, `fast-3b`, `quality-1.7b`, or custom

**Optional Fields**:
- **generation.safety**: Safety constraints (e.g., `require_explicit_sources`, `max_context_chars`)
- **training.batch_size**, **learning_rate**, **epochs**: Hyperparameter overrides
- **evaluation.smoke_prompts**: Custom prompts for smoke tests

**Validation**:
```bash
./ucore validate-spec subjects/my_npc.json
./ucore validate-spec subjects/my_npc.json --strict  # Fail on warnings too
```

---

## Step 2: Generate Dataset

Generate Q&A pairs from your spec using one of several techniques.

### Available Techniques

| Technique | Source | Cost | Speed | Grounding |
|-----------|--------|------|-------|-----------|
| **onyx** | Local Onyx index (repo docs) | Free | Fast | Repo-scoped |
| **docs** | Checked-in markdown files | Free | Fast | Perfect (offline) |
| **ollama** | Local Ollama model | Free | Slow | LLM-generated |
| **notebooklm** | Google NotebookLM API | ~$1-5/spec | Med | Document-based |
| **openai** | OpenAI gpt-4/gpt-3.5 | $$$ | Med | LLM-generated |

### Command Line

```bash
# Generate using local Onyx (default)
./ucore generate subjects/my_npc.json --technique onyx

# Generate using local Ollama model
./ucore generate subjects/my_npc.json --technique ollama

# Generate using docs (for workflow_assistant or custom offline data)
./ucore generate subjects/my_npc.json --technique docs

# Generate using NotebookLM API (requires Google account)
./ucore generate subjects/my_npc.json --technique notebooklm
```

### Dashboard Workflow

1. Open **Workflow Panel** → **Start Workflow**
2. Select **NPC Spec**: `subjects/my_npc.json`
3. Choose **Technique**: `onyx` (or `docs`, `ollama`, etc.)
4. Click **Start** → Dataset generation runs
5. Output: `datasets/my_npc/<technique>/train.jsonl` and `validation.jsonl`

### Output Files

After generation, you'll find:
- **`datasets/my_npc/<technique>/train.jsonl`** — Training data (typically 25–100 Q&A pairs)
- **`datasets/my_npc/<technique>/validation.jsonl`** — Holdout validation set
- **`metadata.json`** — Generation provenance (timestamp, technique, source count, etc.)

---

## Step 3: Sanitize Dataset

Validate ChatML format, clean whitespace, remove duplicates, and ensure data quality.

### Command Line

```bash
./ucore sanitize subjects/my_npc.json \
  --data-path datasets/my_npc/onyx/train.jsonl
```

### Dashboard Workflow

1. **Operations Matrix** → **Sanitize Dataset**
2. Specify dataset path: `datasets/my_npc/onyx/train.jsonl`
3. Click **Start** → Sanitization runs
4. Output: `datasets/my_npc/onyx/train_clean.jsonl` (and validation_clean)

### What Sanitization Checks

- ✅ Valid ChatML structure (roles, content)
- ✅ No truncated or malformed JSON
- ✅ Whitespace normalization
- ✅ Duplicate detection/removal
- ✅ Token count bounds (if configured)
- ✅ Conversation length limits

### Output

- **`train_clean.jsonl`** — Sanitized training set
- **`validation_clean.jsonl`** — Sanitized validation set
- **`sanitize_report.json`** — Statistics (rows in, rows out, discards reason)

---

## Step 4: Validate & Train LoRA Adapter

Validate the config and then fine-tune a base model using Unsloth's efficient LoRA training.

### Validation

```bash
./ucore validate-config subjects/my_npc.json --preset fast-3b
```

### Training Command Line

```bash
# Train with default preset
./ucore train subjects/my_npc.json --preset fast-3b

# Train with specific hyperparameters
./ucore train subjects/my_npc.json \
  --preset custom \
  --epochs 3 \
  --batch-size 2 \
  --lr 0.0003 \
  --lora-r 16 \
  --lora-alpha 32 \
  --model gemma4:e2b

# Train with Weights & Biases logging
./ucore train subjects/my_npc.json --preset fast-3b --wandb
```

### Dashboard Workflow

1. **Workflow Panel** → **Start Workflow**
2. Select **NPC Spec**: `subjects/my_npc.json`
3. Choose **Preset**: `fast-3b` (or `quality-1.7b`, `smoke`, etc.)
4. (Optional) Enable **W&B**: ✓ (tracks metrics + artifacts)
5. Click **Start** → Training pipeline runs (generate → sanitize → train)
6. **Operations Matrix** shows real-time loss, ETA, and status
7. W&B link appears in **Operations Matrix** for inspection

### Training Presets

| Preset | Base Model | Time | Quality | VRAM (6GB) |
|--------|-----------|------|---------|-----------|
| **smoke** | Tiny (124M) | 2 min | Demo-only | ✅ 2.1GB |
| **fast-3b** | Gemma 3B | 15 min | Good | ✅ 5.8GB |
| **quality-1.7b** | Gemma 1.7B | 25 min | Better | ✅ 4.2GB |
| **safe-any** | Auto-select | Var | Safe | ✅ <6GB |

### Training Outputs

Training creates:
- **`outputs/my_npc/best/adapter_model.safetensors`** — Final LoRA weights
- **`outputs/my_npc/best/adapter_config.json`** — Config for the adapter
- **`outputs/my_npc/runs/*/training_metrics.json`** — Loss, accuracy, time
- **`outputs/my_npc/best/config_snapshot.yaml`** — Frozen hyperparameters used

---

## Step 5: Export to GGUF

Convert the fine-tuned LoRA adapter to GGUF format (quantized) for Unity/LLMUnity.

### Command Line

```bash
# Export with quantization (default: q4_k_m)
./ucore export subjects/my_npc.json

# Export with specific quantization
./ucore export subjects/my_npc.json --quant q5_k_m

# Export adapter only (no quantization)
./ucore export-adapter outputs/my_npc/best
```

### Dashboard Workflow

1. **Export & Deployment Panel** → **Export GGUF**
2. Select **NPC Key**: `my_npc`
3. Choose **Quantization**: `q4_k_m` (default) or `q5_k_m`, `q3_k_m`
4. Click **Start** → Export runs
5. Output: `exports/my_npc/my_npc-gemma3b-q4_k_m.gguf`

### Export Outputs

- **`exports/my_npc/<npc_key>-<model>-<quant>.gguf`** — Quantized model for deployment
- **`exports/my_npc/manifest.json`** — Model metadata (size, base model, quant level)

### Deployment

Deploy the GGUF to your Unity project:
```bash
./ucore deploy \
  --unity-project /path/to/unity/project \
  --export-only
```

---

## Full Pipeline: One Command

Run the entire 5-step pipeline in one go:

```bash
./ucore pipeline subjects/my_npc.json \
  --preset fast-3b \
  --technique onyx \
  --wandb
```

This chains:
1. Generate (onyx) → 2. Sanitize → 3. Train (fast-3b) → 4. Evaluate (smoke) → 5. Export

---

## Dashboard: Visual Workflow

The dashboard (`http://localhost:3100`) provides a unified UI:

1. **Workflow Panel** — Start/monitor workflows
   - Pick spec, technique, preset
   - Real-time logs and progress
   - Cancel/retry buttons

2. **Operations Matrix** — Job history
   - All jobs, status, timestamps
   - Loss/ETA for training jobs
   - W&B links for tracked runs
   - Click "Logs" to inspect full stdout/stderr

3. **Export & Deployment** — GGUF export, Unity deployment
   - Select NPC, quantization level
   - Deploy to Unity project (if configured)

4. **Training Suite** — Hyperparameter tuning
   - Build custom presets
   - Adjust LR, batch size, epochs
   - Toggle W&B before launch

5. **Workflow Assistant** (left sidebar)
   - Ask for guidance on any step
   - Load/unload local Ollama model for chat
   - Query Onyx for grounding context

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| **Dataset is empty** | Generation failed or didn't retrieve context | Check Onyx is running; verify spec seeds; try `--technique ollama` |
| **Train OOM (out of memory)** | Model too large for 6GB VRAM | Use smaller preset (`safe-any`, `quality-1.7b`) or `--lora-r 8` |
| **Loss plateaus / doesn't improve** | Insufficient training data or bad hyperparameters | Generate more data; increase `--epochs`; try different `--lr` |
| **Smoke test fails** | Exported GGUF or adapter corrupted | Re-export; check `outputs/my_npc/best/` exists |
| **Dashboard doesn't show job** | Registry cache stale | Restart dashboard server; check `frontend_control/.runtime/registry.json` |

---

## Example: End-to-End Creation

**Goal**: Create a `space_explorer` NPC.

### 1. Create Spec

Create `subjects/space_explorer.json`:
```json
{
  "npc_key": "space_explorer",
  "name": "Space Explorer",
  "identity": "An enthusiastic space historian who teaches about planets, stars, and missions.",
  "llm": { "model_name": "gemma4:e2b" },
  "generation": {
    "prompts": {
      "seed": "What are the characteristics of Jupiter?"
    }
  },
  "training": { "preferred_preset": "fast-3b" }
}
```

### 2. Generate Dataset

CLI:
```bash
./ucore generate subjects/space_explorer.json --technique onyx
```

Or **Dashboard**: Workflow Panel → Spec: `space_explorer` → Technique: `onyx` → Start

### 3. Sanitize

CLI:
```bash
./ucore sanitize subjects/space_explorer.json \
  --data-path datasets/space_explorer/onyx/train.jsonl
```

Or **Dashboard**: Sanitize Dataset → Path: `datasets/space_explorer/onyx/train.jsonl` → Start

### 4. Train

CLI:
```bash
./ucore train subjects/space_explorer.json --preset fast-3b --wandb
```

Or **Dashboard**: Workflow Panel → Spec: `space_explorer` → Preset: `fast-3b` → Enable W&B → Start

### 5. Export

CLI:
```bash
./ucore export subjects/space_explorer.json
```

Or **Dashboard**: Export Panel → NPC: `space_explorer` → Quantization: `q4_k_m` → Start

### 6. Deploy (Optional)

```bash
./ucore deploy --unity-project ~/Projects/MyGame
```

Done! The `space_explorer` NPC is trained, exported, and ready for Unity integration.

---

## Advanced: Custom Reference Documents

If you want to ground your NPC in **custom content** (e.g., astronomy PDFs, company docs), keep the reference content with the NPC dataset and index it into Onyx:

1. Create a reference doc under the NPC dataset folder, for example:
   `datasets/my_npc/onyx/reference_doc/my_npc_reference.md`
2. Index it:
   ```bash
   python scripts/onyx_index_repo.py \
     --npc-key my_npc \
     --document-set my_npc \
     datasets/my_npc/onyx/reference_doc/**/*.md
   ```
3. Generate with scoped retrieval and Onyx prep:
   ```bash
   ./ucore generate subjects/my_npc.json --technique onyx --onyx-prep
   ```

If the NPC has `datasets/{npc_key}/onyx/reference_doc/` files, `--onyx-prep` now automatically includes them during indexing.

---

## Next Steps

- **Read**: [TRAINING_WORKFLOW_CONTEXT.md](TRAINING_WORKFLOW_CONTEXT.md) for detailed preset/config info
- **Explore**: [CLI_REFERENCE.md](reference/CLI_REFERENCE.md) for all CLI flags
- **Integrate**: [EXPORT_WORKFLOW.md](EXPORT_WORKFLOW.md) for Unity deployment details
- **Chat**: Ask the **Workflow Assistant** (dashboard left sidebar) any questions!
