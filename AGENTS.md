# Unsloth_Core: AI Agent Reference Guide

This document is the primary source of truth for AI agents (like Antigravity, Claude, or GPT) working on the **Unsloth_Core** repository. It provides high-level architectural context, command references, and logic maps to ensure efficient collaboration.

## 🚀 Quick Start for Agents
1.  **Activate Env**: `source unsloth_env/bin/activate`
2.  **Verify Setup**: `./ucore audit check`
3.  **Validate Generation Inputs**: `./ucore validate-spec subjects/NPC_specs/history_guide.json --generation-ready`
4.  **Generate Dataset**: `./ucore generate subjects/NPC_specs/history_guide.json --technique template`
5.  **Sanitize Dataset**: `./ucore sanitize subjects/datasets/history_guide/template/train.jsonl --output subjects/datasets/history_guide/template/train_clean.jsonl --strict-canonical --require-complete-metadata`
6.  **Dataset Quality Gate**: `./ucore dataset-eval subjects/NPC_specs/history_guide.json --technique template --judge-model qwen3:latest`
7.  **Smoke Test Pipeline**: `./ucore pipeline subjects/NPC_specs/history_guide.json --preset smoke`
8.  **Production Train**: `./ucore train subjects/NPC_specs/history_guide.json --technique template --preset fast-3b --export-gguf`
9.  **Evaluate Model**: `./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf --spec subjects/NPC_specs/history_guide.json --report-html`

## 📂 Project Logic Map (Where things live)
| Component | Directory / File | Description |
| :--- | :--- | :--- |
| **Unified CLI** | `ucore` | Main entry point for all operations. |
| **Core Scripts** | `scripts/` | Python implementation of the pipeline stages. |
| **NPC Specs** | `subjects/NPC_specs/` | JSON files defining NPC identity and knowledge. |
| **Datasets** | `subjects/datasets/{npc}/{technique}/` | Generated training/validation data (JSONL). `template/` = default dataset directory. |
| **Reference Docs** | `subjects/reference_docs/` | Centralized primer files for grounding dataset generation. |
| **Schemas** | `subjects/schemas/` | JSON Schema validators for training data format. |
| **Training Configs**| `configs/` | YAML base configs and presets. |
| **DeepEval Dataset Gate** | `tests/evals/`, `scripts/dataset/dataset_eval.py` | Local dataset-quality evals using the `qwen3:latest` Ollama judge. |
| **LoRA Adapters** | `outputs/` | Checkpoints and final adapters from training. |
| **GGUF Exports** | `exports/` | LoRA adapter GGUFs (MBs) for Unity/LLMUnity. |
| **Evaluations** | `eval/reports/`, `eval/results/feedback/` | HTML/markdown eval reports, structured per-concept feedback JSON. |
| **Feedback Gaps** | `eval/results/gaps/` | Knowledge gap analysis JSON reports from feedback loop. |
| **Supabase** | `supabase/` | DB migrations and local Docker setup. |
| **Frontend** | `frontend_control/` | Monitoring dashboard and React controls. |
| **llama.cpp** | `~/.unsloth/llama.cpp/` | Prebuilt CUDA binaries: llama-server, llama-quantize, convert_lora_to_gguf.py. |

## 🛠️ The Pipeline (7 Stages + Feedback Loop)
Transforms a subject spec into a playable NPC:

1.  **Generation**: `scripts/dataset/generate_dataset.py`
    - **Template** (default): Fast deterministic generation for pipeline testing.
    - **Docs**: Deterministic generation grounded in curated repo/doc manifests.
    - **Ollama / OpenAI / Anthropic**: Available for LLM-driven synthetic data.
    - Output: `subjects/datasets/{npc_key}/{technique}/train.jsonl`.

2.  **Sanitization**: `scripts/dataset/sanitize_dataset.py`
    - Validates ChatML format, cleans whitespace, removes empty messages.
    - Output: `.../train_clean.jsonl`.

3.  **Dataset Quality Eval**: `scripts/dataset/dataset_eval.py` + `tests/evals/test_dataset_generation_quality.py`
    - Runs DeepEval against `train_clean.jsonl` before training.
    - Default local judge: Ollama `qwen3:latest` (8.2B params) at `http://localhost:11434`.
    - Metrics check persona/category fit and training usefulness/specificity.
    - Outputs: `quality_summary.json` and `quality_failures.json` beside the dataset.
    - Treat `quality_failures.json` as the source of truth for what to regenerate or rewrite. Do not lower thresholds or delete rows to force a pass.

4.  **Training**: `scripts/training/train.py`
    - Unsloth SFTTrainer with LoRA. Config hierarchy: Base YAML < Preset < CLI.
    - Presets: `smoke` (debug), `fast-3b` (standard), `safe-any` (OOM fallback).
    - `--export-gguf` exports adapter GGUF inline after training.
    - Output: `outputs/{npc_key}/` (LoRA adapter) + `exports/{npc_key}/{npc}-lora-f16.gguf`.

5.  **Export & Smoke Test**: `scripts/export/export.py` → `scripts/ops/smoke_test.py`
    - **Adapter mode** (default): Converts LoRA to lightweight GGUF via `convert_lora_to_gguf.py` — MBs, no base model needed.
    - **Full-merge** (`--full-merge-export`): Exports f16 GGUF + quantizes via `llama-quantize`.
    - **Smoke test**: Validates persona adherence via automated prompts.

6.  **Model Evaluation**: `scripts/evaluation/evaluate.py`
    - Starts `llama-server` with `--lora` for adapter evaluation (no full-merge needed).
    - Compares two models (baseline vs candidate) or measures standalone.
    - Supports `--base-model` for LoRA-on-base-model evaluation.
    - Output: HTML report (Chart.js), markdown per-question breakdown, structured feedback JSON.

7.  **Feedback Loop**: `scripts/training/feedback_loop.py` + `scripts/evaluation/evaluate.py --feedback-json`
    - Analyzes eval results → identifies weak concepts → determines gap type:
      - `training_density`: Model didn't learn the topic → regenerate more examples
      - `knowledge_gap`: No relevant reference material → add primer, re-index
    - After regeneration the new dataset is sanitized and gated with `scripts/dataset/dataset_eval.py` before training.
    - Use `--skip-dataset-eval` to bypass the pre-training dataset quality gate.
    - Use `--deepeval-judge-model`, `--deepeval-ollama-url`, and `--deepeval-cases-per-category` to configure the local Ollama judge.
    - Use `--deepeval-soft-fail` to continue training even when the dataset gate reports metric failures.
    - Auto-retrain mode: `./ucore feedback npc.json --auto-retrain --baseline ...`
    - **CRITICAL NOTE (6GB VRAM)**: Do NOT use `--auto-retrain` if doing LLM-grounded generation on an RTX 3060 6GB. Run generation (`--auto`) first, unload Ollama from memory, then manually run training to avoid OOM crashes.
    - Groups results by category/concept for targeted analysis.

### 🔍 Knowledge Gap Detection
| Gap Type | Cause | Fix |
|----------|-------|-----|
| `training_density` | Not enough training examples | Regenerate with `--concept-focus` |
| `knowledge_gap` | Missing reference material | Add reference docs + re-index |

## 🏗️ NPC Scaffold Structure
When creating a new NPC with `./ucore init <npc_key> --subject <subject>`:

```
subjects/NPC_specs/{npc_key}.json                          — spec with 4-section system prompt
subjects/reference_docs/{npc_key}_primer.md       — stub primer for indexing
subjects/datasets/{npc_key}/template/             — smoke/fast datasets only
subjects/datasets/{npc_key}/{technique}/quality_*.json — DeepEval dataset gate reports
outputs/{npc_key}/runs/                           — training checkpoints
exports/{npc_key}/                                — GGUF exports
```

Only `template` technique directory is created. Reference docs are centralized at `subjects/reference_docs/` (not per-NPC).

## 📜 Conventions
- **NPC Keys**: Always `snake_case` (e.g., `history_guide`).
- **GGUF Naming**: `{npc_key}-lora-f16.gguf` (adapter) or `{npc_key}-{model_short}-{quant}.gguf` (full-merge).
- **Quantization**: Default to `q4_k_m` for full-merge; adapter mode uses f16.
- **System Prompt**: 4-section LLMUnity format (IDENTITY | VOICE | KNOWLEDGE | RULES), ~90-105 tokens.
- **Dataset Categories**: Each NPC trains on these 5 categories:
  | Category | Examples | Purpose |
  |----------|----------|---------|
  | identity | 12 | Who the NPC is (personality, background, mannerisms) |
  | teaching | 56 | Subject-matter explanations |
  | dialogue | 32 | Natural conversation handling |
  | quest | 16 | Scenario-based interactions |
  | refusal | 16 | Safe boundary responses |
  **Total: 132 examples** per NPC.
- **Active SFT techniques**: `template`, `docs`, `ollama`, `openai`, `anthropic`.
- **RL data state**: RL preference-pair and reward-rollout schemas exist in `subjects/schemas/`, with the contract in `docs/NPC_DATA_RL_EXECUTION_CONTRACT.md`. Treat RL dataset generation as planned/contracted unless a concrete generator exists in `ucore`.
- **Generation readiness**: `./ucore validate-spec <spec> --generation-ready` must pass before creating new datasets. This enforces reference-doc location/shape, all five categories, and minimum SFT counts.

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
- **Reference-doc contract**: Use `docs/NPC_DATA_RL_EXECUTION_CONTRACT.md` and `subjects/reference_docs/README.md`. A primer must have one H1, at least 5 H2 sections, at least 20 concrete bullets, at least 250 words, and safety/refusal/boundary/misconception notes.
- **Dataset gate before training**: Run `./ucore dataset-eval <spec> --technique <technique>` after sanitize and before SFT. Uses local Ollama `qwen3:latest` as the judge (configured in `tests/evals/metrics.py` and `scripts/dataset/dataset_eval.py`).
- **DeepEval artifacts**: `.deepeval/` is local runtime state and ignored. Dataset gate outputs `quality_summary.json` and `quality_failures.json` are regenerable and ignored.
- **Export mode**: `ucore export <npc_key>` defaults to adapter-only mode. Use `--full-merge` for standalone merged GGUFs.
- **Evaluation**: Use `./ucore evaluate --base-model <base.gguf>` to evaluate adapter GGUFs — no full-merge needed. Uses `llama-server --lora`, same mechanism as LLMUnity runtime. Base GGUF at `Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf`.
- **Preset Selection**:
  - `--preset smoke` for debugging/testing.
  - `--preset fast-3b` for standard NPC training (tuned for RTX 3060 6GB).
  - `--preset safe-any` if CUDA OOM occurs. Use this if Ollama is running in the background, or manually unload Ollama first with `curl http://localhost:11434/api/generate -d '{"model": "llama3.1:latest", "keep_alive": 0}'`.
  - `--wandb` for W&B experiment tracking.
- **llama.cpp toolchain** (`~/.unsloth/llama.cpp/`): Prebuilt CUDA binaries. `llama-server` (inference with `--lora` support), `llama-quantize` (fast local quantization), `convert_lora_to_gguf.py` (adapter export). No `llama-cli` binary.
- **Error Handling**: Check `outputs/{npc_key}/runs/` for TensorBoard logs, `eval/results/` for validation metrics.
- **Before generating a dataset**: Read the `subjects/NPC_specs/*.json` spec and the `subjects/reference_docs/*.md` primer to understand content grounding. If DeepEval fails, fix generation, prompts, concepts, or reference material first; do not change metric thresholds as the first response.

## ⚡ Ollama Performance Tuning

The local Ollama server is tuned for maximum evaluation throughput:

### Environment Variables (systemd override)
Set via `/etc/systemd/system/ollama.service.d/override.conf`:

| Variable | Value | Effect |
|----------|-------|--------|
| `OLLAMA_NUM_PARALLEL` | `4` | 4 concurrent request slots → 5-10x faster DeepEval async evaluation |
| `OLLAMA_FLASH_ATTENTION` | `1` | Enables flash attention (free speed + memory reduction) |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | 8-bit KV cache halves context memory with near-zero quality loss |

### Judge Model Pipeline

| Layer | Model | Params | Quant | Size |
|-------|-------|--------|-------|------|
| **Default judge** (dataset-eval) | `qwen3:latest` | 8.2B | Q4_K_M | 4.9GB |
| **Fallback** (env `OLLAMA_MODEL_NAME`) | `qwen3:latest` | 8.2B | Q4_K_M | 4.9GB |

The judge is configured at three levels (in priority order):
1. CLI flag: `--judge-model qwen3:latest` (passed by `dataset_eval.py`)
2. Env var: `DEEPEVAL_OLLAMA_MODEL` (injected by `dataset_eval.py` before `deepeval test run`)
3. Code default: `"qwen3:latest"` in `tests/evals/metrics.py`

### Restarting Ollama with Tuning
```bash
# The systemd override is already active. To modify:
sudo systemctl stop ollama
# Edit /etc/systemd/system/ollama.service.d/override.conf
# Then:
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

### GPU + CPU Offloading
Ollama (via llama.cpp) automatically distributes model layers between GPU and CPU when VRAM is insufficient. For our RTX 3060 6GB:
- **7-8B models** (Q4_K_M): Full GPU offload (~4.9GB weights + ~1GB KV cache overhead)
- **14B+ models** (Q4_K_M): Partial offload — Ollama auto-partitions layers by available VRAM
- The `num_gpu` parameter (Modelfile or API option) controls explicit layer allocation

To verify GPU utilization:
```bash
ollama ps              # Shows running models and GPU usage
nvidia-smi             # VRAM consumption per process
```

### LM Studio Comparison
Ollama matches LM Studio's offloading capability (both use llama.cpp under the hood) and is **better suited** for our concurrent DeepEval workload:
- `OLLAMA_NUM_PARALLEL` enables native parallel request handling (LM Studio queues sequentially)
- No second service or port needed
- Deeper DeepEval integration via native `OllamaModel` class

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
| NPC | Key | Subject | Current local state |
|-----|-----|---------|---------------------|
| History Guide | `history_guide` | World history | Spec, reference doc, template dataset, exported LoRA GGUFs |
| Chef Assistant | `chef_assistant` | Culinary arts | Spec, reference doc, template dataset, exported LoRA GGUFs |
| Astronomy Guide | `astronomy_guide` | Astronomy and space science | Spec, reference doc, template dataset, exported LoRA GGUF |
| Fitness Coach | `fitness_coach` | Fitness, exercise science, and nutrition | Spec, reference doc, template dataset, exported LoRA GGUF |

Current local exports are adapter GGUFs under `exports/{npc_key}/`. Unity runtime should load the shared base model once and swap LoRA adapters plus the NPC system prompt.

---

## 📚 Key Reference Documents

| Document | Purpose |
|----------|---------|
| `docs/TRAINING_WORKFLOW_CONTEXT.md` | Full training pipeline detail — stages, presets, flags, data flow |
| `README.md` | Project overview and quick start |
| `AGENTS.md` | (this file) Quick-reference for AI agents |

---
*For detailed human-readable guides, see the [README.md](README.md) and the `docs/` directory.*
