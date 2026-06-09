# Platform Integration Reference

Each integrated platform plays a distinct role. This document clarifies **what each platform does**, **what credentials it needs**, **when it runs work vs just logs results**, and **what naming conventions it expects**.

## Quick Reference

| Platform | Role | Runs Work? | Logs Results? | Credentials | Stages |
|----------|------|-----------|---------------|-------------|--------|
| Ollama | Local generation + local judge | Yes (gen, judge) | No | None (local) | generate, dataset-eval |
| W&B | Experiment tracking + hosted judge | Yes (judge) | Yes (train, eval) | `WANDB_API_KEY` | dataset-eval, train, evaluate |
| Confident AI | Eval orchestration + trace observability | Yes (remote eval) | Yes (traces, results) | `CONFIDENT_API_KEY` | dataset-eval, evaluate |
| DeepEval | Evaluation framework (local) | Yes (eval) | Yes (local files) | Optional (`CONFIDENT_API_KEY`) | dataset-eval, evaluate |
| HuggingFace Hub | Base model config downloads | Yes (config fetch) | No | `~/.cache/huggingface/token` | export |
| llama.cpp | Local inference server | Yes (serve) | No | None (local) | generate-local, evaluate |
| Modal | Remote GPU (scaffolded, NOT active) | No | No | `MODAL_TOKEN_ID+SECRET` | — |

---

## 1. Ollama

**Role:** Dataset generation engine + local LLM judge.

**When it runs work:** Always — it's the primary generation backend (`generate-ollama`) and the default local judge for dataset-eval (fast mode).

**When it just logs:** Never — Ollama has no persistent storage or dashboard.

**What it needs:**
- Running server on `http://localhost:11434` (default)
- Model pulled: `qwen2.5:7b` (for judge), `qwen3:latest` (alternative)
- Environment: `OLLAMA_*` vars in `.env` tune server behavior (context length, kv cache, parallelism) but are NOT required

**Naming conventions it expects:**
- Model names: `qwen2.5:7b`, `qwen3:latest`, `llama3.2:3b` (Ollama's `model:tag` convention)
- Model IDs are used directly in CLI flags (`--model qwen2.5:7b`)

**Workflow participation:**
- `./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b` — dataset generation
- `./ucore dataset-eval --judge-provider ollama --judge-model qwen2.5:7b` — dataset quality gate
- `./ucore evaluate --judge --judge-model qwen2.5:7b` — runtime eval

---

## 2. Weights & Biases (W&B)

**Role:** Dual — experiment tracking AND hosted LLM inference.

### Logging mode (`--wandb`)
Logs hyperparameters, loss curves, eval comparisons, and tables to `unsloth-core` project.

### Inference mode (`judge_provider: wandb`)
W&B Serverless Inference runs the judge LLM (`meta-llama/Llama-3.1-70B-Instruct`) on W&B's infrastructure. Used in production profiles when local GPU is insufficient for judging.

**When it runs work:**
- **Inference judge mode** — calls `api.inference.wandb.ai/v1` with a hosted model. This is REAL work, not just logging. Used in production (`npc-production-grounded`) with a 70B model for deep quality judgment.
- **Training** — `wandb.init()` is used to capture training metrics. W&B itself doesn't run the training, but the trainer sends loss data to it.

**When it just logs:**
- Training hyperparameters, eval comparison tables, report HTML artifacts, dataset eval summaries.

**What it needs:**
- `WANDB_API_KEY` env var (or `~/.netrc` for `api.wandb.ai`)
- Entity: `andreabenathar-twl-games` (set in presets + wandb_inference.py)
- Project: `unsloth-core` (default, overridable with `--wandb-project`)

**Naming conventions it expects:**

| Artifact | Pattern | Example |
|----------|---------|---------|
| Training run | `train-{npc_key}-{technique}-{preset}-{run_id}` | `train-chef_assistant-ollama-fast-3b-20260607_001` |
| Eval run | `eval-{npc_key}-{baseline_name}-vs-{candidate_name}` | `eval-chef_assistant-llama3.2-3b-vs-chef_assistant-sft-v2` |
| Quick eval | `quick-eval-{npc_key}` | `quick-eval-chef_assistant` |
| Tags | `["train", npc_key, technique, preset, ...]` | `["train", "chef_assistant", "ollama", "fast-3b"]` |
| Group | `{npc_key}` (default) | `chef_assistant` |

**Workflow participation:**
- `dataset-eval` stage: `--wandb` flag → logs dataset quality metrics + optionally uses W&B Inference as judge
- `train` stage: `--wandb` flag → logs hyperparameters + loss curves
- `evaluate` stage: `--wandb` flag → logs comparison metrics + HTML report

**Profile-specific judge config:**
- Production: `judge_provider: wandb`, `judge_model: meta-llama/Llama-3.1-70B-Instruct` — uses W&B's 70B hosted model for deep eval
- Local: `judge_provider: ollama`, `judge_model: qwen2.5:7b` — uses local Ollama for fast eval

---

## 3. Confident AI (via DeepEval)

**Role:** Evaluation orchestration + trace observability.

### Remote Evaluation (`--confident` / `--remote-eval`)
Evaluates test cases on Confident AI's cloud infrastructure using their metric collections. This ACTUALLY RUNS evaluation work on remote GPUs.

### Trace Observatory (`CONFIDENT_API_KEY` + tracing)
Auto-uploads LangGraph agent traces (spans, metrics) to Confident AI for debugging and observability.

### Dataset Management
Push/pull golden datasets (JSONL) as named datasets for versioned evaluation.

**When it runs work:**
- **Remote eval** (`--remote-eval`): generates and evaluates test cases on Confident AI infra
- **Push/pull goldens**: pushes local datasets to Confident AI for reference comparison

**When it just logs:**
- **Trace uploads**: traces instrumented with `@trace_agent_node` auto-upload
- **Local eval results**: results are mirrored to Confident AI when `--confident` is passed

**Naming conventions it expects:**

| Artifact | Pattern | Example |
|----------|---------|---------|
| Metric Collection | `npc-{domain}-quality` | `npc-dataset-quality`, `npc-model-quality` |
| Dataset Alias | `ucore-{npc_key}-{technique}-{suffix}` | `ucore-history-guide-template-single-v1` |
| Test Run ID | `{type}-{npc_key}-{technique}-{mode}-{timestamp}` | `dataset-quality-chef_assistant-ollama-release-20260609T120000Z` |
| Classifier set | Defined in Confident UI | `NPC Dataset Failure Mode`, `NPC Dataset Strength`, `NPC Repair Priority` |

**Metric collections (hardcoded in code):**

| Collection Name | Used By | Metrics |
|----------------|---------|---------|
| `npc-dataset-quality` | `dataset_eval.py` | answer_relevancy, faithfulness, hallucination |
| `npc-conversation-quality` | `dataset_eval.py` | role_adherence, knowledge_retention, conversation_completeness |
| `npc-model-quality` | `evaluate.py` | answer_relevancy, faithfulness |
| `unsloth-core-dataset-repair` | `confident_insights.py` | Persona and Category Fit, Training Usefulness, Grounding, Runtime Constraint |

**Workflow participation:**
- `dataset-eval` stage: `--confident` → uploads results; `--remote-eval` → runs eval on Confident infra
- `evaluate` stage: `--deepeval` → runs DeepEval model quality evaluation; `--remote-eval` → runs on Confident infra

---

## 4. HuggingFace Hub

**Role:** Base model config downloader — and nothing else.

**When it runs work:** During GGUF export, downloads `config.json` from HuggingFace for the base model. Without this, `convert_lora_to_gguf.py` can't produce a valid LoRA adapter GGUF.

**When it just logs:** Never.

**Naming conventions it expects:**
- Model IDs: `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` (org/model-name format)
- `model_short_name()` derives short names: `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` → `llama3.2-3b`
- Token file: `~/.cache/huggingface/token`

**Workflow participation:**
- `export` stage only — fetches base model config for converter

---

## 5. Modal

**Role:** **Scaffolded, NOT active.** Intended for remote GPU pipeline execution.

- `enabled: false, required: false` in every integration check
- `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` credentials exist in `.env` but no code uses them
- No Modal profile in `npc-production-strategy.yaml`
- `system_suffix()` has `_Md` ready for when it's activated

**When activated, would run:** Training, dataset eval, and runtime eval remotely on GPU instances.

---

## 6. llama.cpp

**Role:** Local inference server for `generate-local` workflow.

- Started via `~/llama-servers.sh` on an arbitrary port
- Serves OpenAI-compatible API (`/v1/chat/completions`)
- Used as an alternative to Ollama when more GPU control is needed

**Workflow participation:**
- `generate-local` stage: `./ucore generate-local --model <gguf> data/npcs/specs/<npc>.json`

---

## Platform Decision Matrix

| Decision Point | Local (dev) | Production |
|---------------|-------------|------------|
| Generation | Ollama (`qwen2.5:7b`) or llama.cpp | Ollama (`qwen2.5:7b`) — no change |
| Dataset judge | Ollama (`qwen2.5:7b`, fast mode) | W&B Inference (`meta-llama/Llama-3.1-70B-Instruct`) — deeper quality gate |
| Training tracker | — | W&B logging |
| Eval judge | Ollama (`qwen2.5:7b`) | W&B Inference (70B) |
| Eval results | Local files + HTML report | Local files + Confident AI + W&B |
| Remote GPU | — | Future: Modal |

---

## `system_suffix()` — Platform Encoding in Filenames

The `system_suffix()` helper in `src/config/paths.py` encodes which external systems
produced an artifact. Use this when an artifact involves a non-local system:

| System | Suffix | When to use |
|--------|--------|-------------|
| Local (default) | *(none)* | All generation, training, and eval done locally |
| Confident AI | `_C` | Eval results uploaded to Confident AI |
| W&B | `_Wb` | Judge or logging used W&B infrastructure |
| Modal | `_Md` | GPU workload ran on Modal (future) |
| Combined | `_CWb` | Confident AI + W&B both involved |
| Combined+Modal | `_CWbMd` | All three |

**Rule of thumb:** If the pipeline stage touched a non-local system (even for logging),
add the suffix. Pure local runs get no suffix (it's the implicit default).
