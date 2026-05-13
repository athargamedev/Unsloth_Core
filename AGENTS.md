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
| **Datasets** | `datasets/` | Generated training and validation data (JSONL). |
| **Training Configs**| `configs/` | YAML base configs and presets. |
| **LoRA Adapters** | `outputs/` | Checkpoints and final adapters from training. |
| **GGUF Exports** | `exports/` | Quantized models for Unity deployment. |
| **Evaluations** | `eval/` | Reports, results, and comparison metrics. |
| **Supabase** | `supabase/` | DB migrations and local Docker setup. |
| **Frontend** | `frontend_control/` | Monitoring dashboard and React controls. |

## 🛠️ The 4-Stage Pipeline
The project follows a deterministic workflow to transform a subject spec into a playable NPC:

1.  **Generation**: `scripts/generate_dataset.py`
    - Uses NotebookLM API (default), Ollama, or OpenAI to generate Q&A pairs.
    - Output: `datasets/{npc_key}/{technique}/train.jsonl`.
2.  **Sanitization**: `scripts/sanitize_dataset.py`
    - Validates ChatML format, cleans white-space, and ensures dataset integrity.
    - Output: `.../train_clean.jsonl`.
3.  **Training**: `scripts/train.py`
    - Uses Unsloth SFTTrainer with LoRA for efficient fine-tuning.
    - Supports hierarchical configs (Base YAML < Preset < CLI).
    - Output: `outputs/{npc_key}/` (LoRA adapter).
4.  **Export & Validation**: `scripts/export.py` & `scripts/smoke_test.py`
    - Converts LoRA + Base Model to quantized GGUF.
    - Validates persona adherence via automated smoke tests.

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
- **Preset Selection**:
  - Use `--preset smoke` for debugging/testing.
  - Use `--preset fast-3b` for standard NPC training.
  - Use `--preset safe-any` if CUDA OOM occurs.
- **Context Awareness**: Before generating a dataset, read the `subjects/*.json` spec to ensure the generated data aligns with the NPC's `identity` and `teaching` style.
- **Error Handling**: If training fails, check `outputs/{npc_key}/runs/` for TensorBoard logs or `eval/results/` for validation metrics.

## 📜 Conventions
- **NPC Keys**: Always `snake_case` (e.g., `bible_instructor`).
- **GGUF Naming**: `{npc_key}-{model_short}-{quant}.gguf`.
- **Quantization**: Default to `q4_k_m`.

---
*For detailed human-readable guides, see the [README.md](README.md) and the `docs/` directory.*