# Unsloth_Core: AI Agent Reference Guide

This document is the primary source of truth for AI agents (like Antigravity, Claude, or GPT) working on the **Unsloth_Core** repository. It provides high-level architectural context, command references, and logic maps to ensure efficient collaboration.

## 🚀 Quick Start for Agents
1.  **Activate Env**: `source unsloth_env/bin/activate`
2.  **Verify Setup**: `./ucore pipeline subjects/chemistry_instructor.json --preset smoke`
3.  **Local Training**: `./ucore train subjects/chemistry_instructor.json --preset fast-3b`
4.  **Smoke Test**: `./ucore smoke exports/chemistry_instructor/...gguf --spec subjects/chemistry_instructor.json`

## 📂 Project Logic Map (Where things live)
| Component | Directory / File | Description |
| :--- | :--- | :--- |
| **Unified CLI** | `ucore` | Main entry point for all operations. |
| **Core Scripts** | `scripts/` | Python implementation of the pipeline stages. |
| **NPC Specs** | `subjects/` | JSON files defining NPC identity and knowledge. |
| **Datasets** | `subjects/datasets/` | Generated training and validation data (JSONL). |
| **Reference Docs** | `subjects/reference_docs/` | Centralized reference materials for NotebookLM generation. |
| **Schemas** | `subjects/schemas/` | JSON Schema validators for training data format. |
| **Training Configs**| `configs/` | YAML base configs and presets. |
| **LoRA Adapters** | `outputs/` | Checkpoints and final adapters from training. |
| **GGUF Exports** | `exports/` | Quantized models (full-merge) or LoRA adapters (default) for Unity. |
| **Evaluations** | `eval/` | Reports, results, and comparison metrics. |
| **Supabase** | `supabase/` | DB migrations and local Docker setup. |
| **Frontend** | `frontend_control/` | Monitoring dashboard and React controls. |
| **llama.cpp** | `~/.unsloth/llama.cpp/` | Prebuilt binaries: llama-server, llama-quantize, convert_lora_to_gguf.py. |

## 🛠️ The 5-Stage Pipeline
The project follows a deterministic workflow to transform a subject spec into a playable NPC:

1.  **Generation**: `scripts/generate_dataset.py`
    - Uses NotebookLM API (default), Ollama, or OpenAI to generate Q&A pairs.
    - Output: `subjects/datasets/{npc_key}/{technique}/train.jsonl`.
2.  **Sanitization**: `scripts/sanitize_dataset.py`
    - Validates ChatML format, cleans white-space, and ensures dataset integrity.
    - Output: `.../train_clean.jsonl`.
3.  **Training**: `scripts/train.py`
    - Uses Unsloth SFTTrainer with LoRA for efficient fine-tuning.
    - Supports hierarchical configs (Base YAML < Preset < CLI).
    - Use `./ucore plan-execution --spec ... --preset ...` before long runs to choose local vs remote_colab.
    - Training automatically exports to GGUF (adapter-only mode by default, use `--full-merge-export` for standalone GGUF).
    - Output: `outputs/{npc_key}/` (LoRA adapter).
4.  **Export & Smoke Test**: `scripts/export.py` → `scripts/smoke_test.py`
    - **Default (adapter)**: Converts LoRA to lightweight GGUF via `convert_lora_to_gguf.py` — fast, no base model loading (MBs, for Unity/LLMUnity).
    - **Full-merge** (`--full-merge-export`): Exports f16 GGUF via unsloth once, then uses `llama-quantize` from `~/.unsloth/` for additional quant levels.
    - **Validation**: `scripts/smoke_test.py` validates persona adherence via automated smoke tests.
5.  **Evaluation** (new): `scripts/track_eval_results.py` + `scripts/compare_runs.py`
    - Tracks results in `eval/results/` for baseline comparison.
    - Compares iterations with `./ucore compare-runs`.
    - The `ucore pipeline` command now runs all 5 stages and supports `--skip-smoke`, `--skip-eval`, `--full-merge-export`.

## 💾 Supabase Integration
A local Supabase instance tracks everything:
- **`npc_profiles`**: Central catalog of all NPCs.
- **`dialogue_sessions`**: Active conversation state.
- **`npc_memories`**: Vector-searchable semantic memory.
- **`test_results`**: Evaluation metrics for every run.

**Useful Commands:**
- `supabase start`: Start local Docker services.
- `./ucore supabase-check --npc-key chemistry_instructor`: Verify profile alignment.

## 🤖 AI Agent Best Practices
- **Always use `ucore`**: Prefer the unified CLI over direct script calls when possible.
- **Export mode**: `ucore export <npc_key>` defaults to adapter-only mode (fast, lightweight GGUF for Unity/LLMUnity). Use `ucore export <npc_key> --full-merge` for standalone merged GGUFs.
- **Training + export**: `./ucore train ... --export-gguf` uses adapter mode automatically. Use `--full-merge-export` for full merged GGUF after training.
- **Preset Selection**:
  - Use `--preset smoke` for debugging/testing.
  - Use `--preset fast-3b` for standard NPC training.
  - Use `--preset safe-any` if CUDA OOM occurs.
  - Use `--preset wandb` (or `--wandb`) for W&B experiment tracking.
- **llama.cpp toolchain** (`~/.unsloth/llama.cpp/`): Prebuilt CUDA binaries. Contains `llama-server` (inference), `llama-quantize` (fast local quantization from f16→q4_k_m etc.), `convert_lora_to_gguf.py` (adapter export). No `llama-cli` binary. Used by: export (converter), smoke tests (server), eval (server), full-merge quantization.
- **Context Awareness**: Before generating a dataset, read the `subjects/*.json` spec to ensure the generated data aligns with the NPC's `identity` and `teaching` style.
- **Error Handling**: If training fails, check `outputs/{npc_key}/runs/` for TensorBoard logs or `eval/results/` for validation metrics. W&B run links appear in the dashboard Operations Matrix and in the console output.

## 📊 W&B Integration
Weights & Biases tracks every training run with:
- **Config snapshot**: Full frozen training config logged as a run file.
- **Metrics**: Loss, learning rate, and any HF Trainer-reported scalars (logged at each eval step).
- **Dataset artifact**: Dataset JSONL as a W&B artifact (versioned by content hash, technique, row count).
- **LoRA artifact**: Final adapter weights as a `lora-{npc_key}` artifact.
- **GGUF artifact**: Exported quantized model as a `gguf-{npc_key}` artifact (when `--export-gguf` is used).

**Dashboard integration:**
- All training runs launched with `--wandb` get a clickable W&B link in the frontend Operations Matrix.
- The frontend SPA (`frontend_control/unity-npc-llm-training-dashboard/`) runs on localhost:3100 and provides:
  - Operations Matrix with pipeline control
  - Training Suite hyperparameter panel
  - TensorBoard charts and W&B links
  - GPU telemetry and system monitoring
- The legacy `ucore dashboard` command has been removed. Use the React SPA at localhost:3100 instead.

## 🖥️ Frontend Dashboard
The dashboard at `http://localhost:3100` provides:
- **Operations Matrix**: Real-time job table with Loss/Progress/Status columns, W&B link per run.
- **Training Suite**: Hyperparameter config panel with W&B toggle.
- **TensorBoard Panel**: Live loss/accuracy/LR charts from TensorBoard event files.
- **System Hub**: Command launcher for all pipeline stages.
- **Log streaming**: Real-time stdout/stderr capture with 2,000-line per-job buffer, debounced persistence, and auto-extraction of W&B URLs and loss values.

## 📜 Conventions
- **NPC Keys**: Always `snake_case` (e.g., `bible_instructor`).
- **GGUF Naming**: `{npc_key}-{model_short}-{quant}.gguf`.
- **Quantization**: Default to `q4_k_m`.

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