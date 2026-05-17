# Unsloth_Core: AI Agent Reference Guide

This document is the primary source of truth for AI agents (like Antigravity, Claude, or GPT) working on the **Unsloth_Core** repository. It provides high-level architectural context, command references, and logic maps to ensure efficient collaboration.

## 🚀 Quick Start for Agents
1.  **Activate Env**: `source unsloth_env/bin/activate`
2.  **Verify Setup**: `./ucore audit check`
3.  **Smoke Test Pipeline**: `./ucore pipeline subjects/history_guide.json --preset smoke`
4.  **Production Train**: `./ucore train subjects/history_guide.json --technique onyx --preset fast-3b --export-gguf`
5.  **Evaluate**: `./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf --spec subjects/history_guide.json --report-html`

## 📂 Project Logic Map (Where things live)
| Component | Directory / File | Description |
| :--- | :--- | :--- |
| **Unified CLI** | `ucore` | Main entry point for all operations. |
| **Core Scripts** | `scripts/` | Python implementation of the pipeline stages. |
| **NPC Specs** | `subjects/` | JSON files defining NPC identity and knowledge. |
| **Datasets** | `subjects/datasets/{npc}/{technique}/` | Generated training/validation data (JSONL). `onyx/` = production, `template/` = smoke. |
| **Reference Docs** | `subjects/reference_docs/` | Centralized primer files for Onyx indexing and RAG generation. |
| **Schemas** | `subjects/schemas/` | JSON Schema validators for training data format. |
| **Training Configs**| `configs/` | YAML base configs and presets. |
| **LoRA Adapters** | `outputs/` | Checkpoints and final adapters from training. |
| **GGUF Exports** | `exports/` | LoRA adapter GGUFs (MBs) for Unity/LLMUnity. |
| **Evaluations** | `eval/reports/`, `eval/results/feedback/` | HTML/markdown eval reports, structured per-concept feedback JSON. |
| **Feedback Gaps** | `eval/results/gaps/` | Knowledge gap analysis JSON reports from feedback loop. |
| **Supabase** | `supabase/` | DB migrations and local Docker setup. |
| **Frontend** | `frontend_control/` | Monitoring dashboard and React controls. |
| **llama.cpp** | `~/.unsloth/llama.cpp/` | Prebuilt CUDA binaries: llama-server, llama-quantize, convert_lora_to_gguf.py. |

## 🛠️ The Pipeline (5 Stages + Feedback Loop)
Transforms a subject spec into a playable NPC:

1.  **Generation**: `scripts/generate_dataset.py`
    - **Onyx** (production): Retrieves context from indexed reference docs via local Onyx server, generates grounded Q&A pairs. Natural conversation templates (v2) with deterministic variant selection via `_pick_variant()`.
    - **Template** (smoke only): Fast deterministic generation for pipeline testing. Never train production LoRAs on template data.
    - Output: `subjects/datasets/{npc_key}/{technique}/train.jsonl`.

2.  **Sanitization**: `scripts/sanitize_dataset.py`
    - Validates ChatML format, cleans whitespace, removes empty messages.
    - Output: `.../train_clean.jsonl`.

3.  **Training**: `scripts/train.py`
    - Unsloth SFTTrainer with LoRA. Config hierarchy: Base YAML < Preset < CLI.
    - Presets: `smoke` (debug), `fast-3b` (standard), `safe-any` (OOM fallback).
    - `--export-gguf` exports adapter GGUF inline after training.
    - Output: `outputs/{npc_key}/` (LoRA adapter) + `exports/{npc_key}/{npc}-lora-f16.gguf`.

4.  **Export & Smoke Test**: `scripts/export.py` → `scripts/smoke_test.py`
    - **Adapter mode** (default): Converts LoRA to lightweight GGUF via `convert_lora_to_gguf.py` — MBs, no base model needed.
    - **Full-merge** (`--full-merge-export`): Exports f16 GGUF + quantizes via `llama-quantize`.
    - **Smoke test**: Validates persona adherence via automated prompts.

5.  **Evaluation**: `scripts/evaluate.py`
    - Starts `llama-server` with `--lora` for adapter evaluation (no full-merge needed).
    - Compares two models (baseline vs candidate) or measures standalone.
    - Supports `--base-model` for LoRA-on-base-model evaluation.
    - Output: HTML report (Chart.js), markdown per-question breakdown, structured feedback JSON.

6.  **Feedback Loop**: `scripts/feedback_loop.py` + `scripts/evaluate.py --feedback-json`
    - Analyzes eval results → identifies weak concepts → determines gap type:
      - `training_density`: Onyx has docs, model didn't learn → regenerate more examples
      - `knowledge_gap`: Onyx has no relevant docs → add primer, re-index
    - Auto-retrain mode: `./ucore feedback npc.json --auto-retrain --baseline ...`
    - Groups results by category/concept for targeted analysis.

### 🔍 Knowledge Gap Detection
| Gap Type | Onyx Has Docs? | Cause | Fix |
|----------|---------------|-------|-----|
| `training_density` | Yes | Not enough training examples | Regenerate with `--concept-focus` |
| `knowledge_gap` | No | Missing reference material | Add reference docs + re-index |

## 🏗️ NPC Scaffold Structure
When creating a new NPC with `./ucore init <npc_key> --subject <subject>`:

```
subjects/{npc_key}.json                          — spec with 4-section system prompt
subjects/reference_docs/{npc_key}_primer.md       — stub primer for Onyx indexing
subjects/datasets/{npc_key}/onyx/                 — production Onyx-grounded datasets
subjects/datasets/{npc_key}/template/             — smoke/fast datasets only
outputs/{npc_key}/runs/                           — training checkpoints
exports/{npc_key}/                                — GGUF exports
```

Only `onyx` and `template` technique directories are created. Reference docs are centralized at `subjects/reference_docs/` (not per-NPC).

## 📜 Conventions
- **NPC Keys**: Always `snake_case` (e.g., `history_guide`).
- **GGUF Naming**: `{npc_key}-lora-f16.gguf` (adapter) or `{npc_key}-{model_short}-{quant}.gguf` (full-merge).
- **Quantization**: Default to `q4_k_m` for full-merge; adapter mode uses f16.
- **System Prompt**: 4-section LLMUnity format (IDENTITY | VOICE | KNOWLEDGE | RULES), ~90-105 tokens.
- **Dataset Categories**: Each NPC trains on these 5 categories:
  | Category | Examples | Purpose |
  |----------|----------|---------|
  | identity | 8 | Who the NPC is (personality, background, mannerisms) |
  | teaching | 32 | Subject-matter explanations |
  | dialogue | 16 | Natural conversation handling |
  | quest | 8 | Scenario-based interactions |
  | refusal | 8 | Safe boundary responses |
  **Total: 72 examples** per NPC (Onyx production dataset).

## 💾 Supabase Integration (optional)
A local Supabase instance can track:
- **`npc_profiles`**: Central catalog of all NPCs.
- **`dialogue_sessions`**: Active conversation state.
- **`npc_memories`**: Vector-searchable semantic memory.
- **`test_results`**: Evaluation metrics for every run.

**Useful Commands:**
- `supabase start`: Start local Docker services.
- `./ucore supabase-check --npc-key history_guide`: Verify profile alignment.

## 🤖 AI Agent Best Practices
- **Always use `ucore`**: Prefer the unified CLI over direct script calls.
- **Export mode**: `ucore export <npc_key>` defaults to adapter-only mode. Use `--full-merge` for standalone merged GGUFs.
- **Evaluation**: Use `./ucore evaluate --base-model <base.gguf>` to evaluate adapter GGUFs — no full-merge needed. Uses `llama-server --lora`, same mechanism as LLMUnity runtime. Base GGUF at `Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf`.
- **Preset Selection**:
  - `--preset smoke` for debugging/testing.
  - `--preset fast-3b` for standard NPC training (tuned for RTX 3060 6GB).
  - `--preset safe-any` if CUDA OOM occurs.
  - `--wandb` for W&B experiment tracking.
- **llama.cpp toolchain** (`~/.unsloth/llama.cpp/`): Prebuilt CUDA binaries. `llama-server` (inference with `--lora` support), `llama-quantize` (fast local quantization), `convert_lora_to_gguf.py` (adapter export). No `llama-cli` binary.
- **Onyx Generation v2**: Uses natural conversation templates (not "Based on our material:" framing). Deterministic variant selection via `_pick_variant()` using `hash(f"{concept}:{category}")`. Content cleaner strips all markdown headings, bold markers, list prefixes.
- **Error Handling**: Check `outputs/{npc_key}/runs/` for TensorBoard logs, `eval/results/` for validation metrics.
- **Before generating a dataset**: Read the `subjects/*.json` spec and the `subjects/reference_docs/*.md` primer to understand content grounding.

## 📊 W&B Integration
Weights & Biases tracks every training run with:
- **Config snapshot**: Full frozen training config logged as a run file.
- **Metrics**: Loss, learning rate, HF Trainer-reported scalars.
- **Dataset artifact**: Dataset JSONL versioned by content hash, technique, row count.
- **LoRA artifact**: Final adapter weights as `lora-{npc_key}` artifact.
- **GGUF artifact**: Exported GGUF as `gguf-{npc_key}` artifact.

**Dashboard:** Runs at `http://localhost:3100` (React SPA in `frontend_control/`):
- Operations Matrix with pipeline control, W&B links, real-time job table
- Training Suite hyperparameter panel
- TensorBoard charts and W&B links
- GPU telemetry and system monitoring

## 🖥️ Active NPCs
| NPC | Key | Subject | Loss (Onyx v2) | Eval vs Template |
|-----|-----|---------|----------------|-----------------|
| History Guide | `history_guide` | World history | 1.771 | 25% win rate |
| Chef Assistant | `chef_assistant` | Culinary arts | 1.768 | 12% win rate |

Active focus is now the two simple NPC datasets above. Space Guide was removed from `subjects/`, `outputs/`, and `exports/` to keep the project focused.

The two active NPCs are deployed as LoRA GGUFs to Unity StreamingAssets. Base model: `llama-3.2-3b-instruct-q4_k_m.gguf` (1.9 GB). Runtime loads base once + LoRAs; switching is instant via system prompt + adapter swap in `NPCLoraAgent`.

---

## 📚 Key Reference Documents

| Document | Purpose |
|----------|---------|
| `docs/TRAINING_WORKFLOW_CONTEXT.md` | Full training pipeline detail — stages, presets, flags, data flow, Onyx integration |
| `docs/ONYX_WORKFLOW.md` | Onyx setup, indexing, and RAG-based generation workflow |
| `README.md` | Project overview and quick start |
| `AGENTS.md` | (this file) Quick-reference for AI agents |

---
*For detailed human-readable guides, see the [README.md](README.md) and the `docs/` directory.*
