# Unsloth_Core: AI Agent Reference Guide

This document is the primary source of truth for AI agents (like Antigravity, Claude, or GPT) working on the **Unsloth_Core** repository. The project north star is to produce the best GGUF LoRA adapters for the llama3.2 3B base model so Unity NPCs can load at runtime in LLMUnity and manage dialogue sessions through local Supabase.

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
| **Auth & API Keys** | `src/backend/middleware/auth.ts`, `src/backend/routes/auth.ts` | Bearer token auth with bcrypt, role-based access (admin/operator/viewer), API key management endpoints (GET/POST/DELETE /api/auth/keys) |
| **Audit Logging** | `src/backend/middleware/audit.ts` | Automatic audit logging to `api_audit_log` table — captures method, path, status, body (with sensitive field redaction), IP, duration |
| **Core Scripts** | `scripts/` | Python implementation of the pipeline stages. |
| **Dashboard Auth** | `scripts/ops/setup_admin_key.py` | Bootstrap script to generate the initial admin API key (stores bcrypt hash in `api_keys` table, key passed via stdin not env vars) |
| **Dashboard Enhancement** | `src/components/NotificationCenter.tsx`, `src/components/GlobalSearch.tsx`, `src/components/LoadingSpinner.tsx`, `src/components/EmptyState.tsx` | Toast notification system (bell icon, auto-dismiss, type-colored), Ctrl+K global search across NPCs/datasets/runs/exports/jobs, loading spinner, empty state components |
| **Datasets** | `subjects/datasets/{npc}/{technique}/` | Generated training/validation data (JSONL). `template/` = default dataset directory. |
| **DeepEval Dataset Gate** | `tests/evals/`, `scripts/dataset/dataset_eval.py` | Local dataset-quality evals using the `qwen3:latest` Ollama judge. |
| **Evaluations** | `eval/reports/`, `eval/results/feedback/` | HTML/markdown eval reports, structured per-concept feedback JSON. |
| **Feedback Gaps** | `eval/results/gaps/` | Knowledge gap analysis JSON reports from feedback loop. |
| **Frontend** | `frontend_control/` | Monitoring dashboard and React controls. |
| **GGUF Exports** | `exports/` | LoRA adapter GGUFs (MBs) for Unity/LLMUnity. |
| **Keyboard Shortcuts** | `src/hooks/useKeyboardShortcuts.ts` | Ctrl+K (search), Ctrl+S (stop all jobs), Alt+1-4 (navigate tabs), Ctrl+R (refresh data) — input-aware (ignored when input focused) |
| **llama.cpp** | `~/.unsloth/llama.cpp/` | Prebuilt CUDA binaries: llama-server, llama-quantize, convert_lora_to_gguf.py. |
| **LoRA Adapters** | `outputs/` | Checkpoints and final adapters from training. |
| **Modular Backend** | `src/backend/` | 27-file modular Express backend under `src/backend/` (routes/, services/, middleware/, lib/) — additive alongside existing server.ts |
| **Modular Entry Point** | `server-modular.ts` | Production-ready Express server wiring modular backend with CORS, rate limiting, security headers, Vite dev middleware, job queue, and graceful shutdown |
| **NPC Specs** | `subjects/NPC_specs/` | JSON files defining NPC identity and knowledge. |
| **Pipeline DB (Python)** | `scripts/ops/pipeline_db.py` | Dual-mode DB client (direct PostgreSQL via psycopg2 + REST API fallback) for all pipeline tables — 20 methods, auto-detection from env vars, filesystem sync |
| **Pipeline DB Tables** | `supabase/migrations/20260521000001_create_pipeline_tables.sql` | 8 pipeline tables: `pipeline_jobs`, `pipeline_runs`, `pipeline_artifacts`, `dataset_quality_gates`, `eval_sessions`, `pipeline_config_snapshots`, `api_keys`, `api_audit_log` — with 3 helper functions, 14 indexes, 8 RLS policies |
| **React Query Hooks** | `src/hooks/useReactQuery.ts`, `src/hooks/useWebSocketQuery.ts` | React Query wrappers for 11 API endpoints + 6 mutations; WebSocket-to-React-Query bridge with stale-time management |
| **Reference Docs** | `subjects/reference_docs/` | Centralized primer files for grounding dataset generation. |
| **Schemas** | `subjects/schemas/` | JSON Schema validators for training data format. |
| **Supabase** | `supabase/` | DB migrations and local Docker setup. |
| **Training Configs**| `configs/` | YAML base configs and presets. |
| **Unified CLI** | `ucore` | Main entry point for all operations. |
| **Workflow Chaining** | `src/backend/routes/workflow.ts` (chainToNextStep), `src/backend/services/job-queue.ts` | Multi-step workflow chaining (generate → sanitize → train → export) with auto-progression, DB-persistent job queue with PID liveness checks, FOR UPDATE SKIP LOCKED polling, exponential backoff retry |
| **Workflow Hooks** | `scripts/ops/workflow_hooks.py` | Lifecycle recording for all pipeline stages via step() context managers. `WorkflowHookReader` for parsing hook JSONL. |
| **Zustand Store** | `src/stores/app-store.ts` | UI state management (tabs, filters, toasts, selection, recent searches with localStorage persistence) |

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

## 🔍 Workflow Hook System

Every pipeline script records its lifecycle in a `workflow_hooks.jsonl` file co-located with the stage output (e.g., alongside the dataset for generation, beside the adapter for training). The hook system replaces the previous ad-hoc `emit(start/complete)` pattern with a clean context manager convention.

### Core API

- **`WorkflowHookRecorder`** (`scripts/ops/workflow_hooks.py`): Entry point for recording. Instantiated per pipeline run, accepts `spec_path` and `run_id` that propagate through all events.
- **`WorkflowHookReader`**: Companion class for consuming hook files. Provides:
  - `read()` — parse all events from a JSONL file
  - `group_by_trace()` — group events by trace ID for per-run analysis
  - `trace_summary(trace_id)` — summary of a single trace with elapsed time, status, and step count
  - `pipeline_summary(path)` — entry point returning `{"total_events": int, "traces": list[dict]}`

### `step()` Context Manager Convention

All 11 pipeline scripts use the `with hook_recorder.step(...)` pattern:

```python
with hook_recorder.step("generate_dataset", spec_path=spec, run_id=run_id) as ctx:
    ctx.log("Starting generation...")
    # ... pipeline work ...
    # No explicit emit() needed — step() records start on enter,
    # complete on normal exit, or error on (Exception, SystemExit)
```

The context manager:
- Captures `start` event on entry (with timestamp, spec_path, run_id)
- Captures `complete` event on clean exit
- Captures `error` event on `(Exception, SystemExit)` — ensuring error exits are never missed
- Supports `ctx.log(message)` for intermediate diagnostic messages

### `FeedbackLoopExit` Pattern

The feedback loop (`scripts/training/feedback_loop.py`) uses a custom `FeedbackLoopExit` exception for early termination paths that should record an `"error"` status in the hooks (as opposed to a clean `"complete"`). This ensures the hook file accurately reflects that the feedback loop exited early with a decision (e.g., "no gaps to address") rather than succeeding.

### Documented Exception: `batch_export.py`

`scripts/export/batch_export.py` uses per-sub-step `emit()` calls instead of the `step()` context manager because it processes multiple export targets in a single run and needs fine-grained event recording for each sub-step. This is the only exception to the `step()` convention.

### Reading Hook Files

```python
from scripts.ops.workflow_hooks import WorkflowHookReader

summary = WorkflowHookReader.pipeline_summary("outputs/history_guide/runs/run_20260520_123456/workflow_hooks.jsonl")
# Returns: {"total_events": 24, "traces": [{"trace_id": "...", "steps": [...], "status": "complete", "elapsed": 12.34}, ...]}
```

### CLI Flag

Pipeline scripts accept `--workflow-hooks <path>` to specify a custom output path for the hook JSONL. When omitted, the default path is derived from the stage output directory.

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
- **Dataset/Eval Decision Rules**: Do not increase NPC sentence/character limits to force generation success. Do not lower dataset minimums to hide missing rows. If generation misses rows, fix generator retry/repair/sanitize behavior or report the gap explicitly. If DeepEval fails, fix prompts, primers, concepts, or generated rows; do not weaken thresholds first.
- **Frontend trust rule**: The dashboard must reflect canonical backend state and process artifacts so non-coder developers can operate the workflow intuitively.
- **Local Ollama rule**: Benchmark and tune local Ollama on this machine before claiming the need for remote capacity; measure tokens/sec, latency, VRAM use, loaded models, and failure rate.
- **Hook system**: All pipeline scripts record lifecycle events in `workflow_hooks.jsonl` via `step()` context managers. Use `WorkflowHookReader.pipeline_summary(path)` to read. Hook files contain start/complete/error events per step with timing, `spec_path`, `run_id`, and step-specific metadata.
- **Auth**: After a fresh Supabase migration, run `python scripts/ops/setup_admin_key.py` to create the initial admin API key. Use the key with `curl -H "Authorization: Bearer <key>"` for all /api calls.
- **Modular backend**: Prefer `npm run dev:modular` over `npm run dev` for new work — the modular backend (`server-modular.ts`) includes auth, rate limiting, audit logging, and a job queue. The legacy `server.ts` remains for backward compatibility.
- **Job queue**: All pipeline operations use `JobQueue` from `src/backend/services/job-queue.ts` for process lifecycle management. Jobs survive server restarts. Monitor at `/api/jobs`.
- **Code review gates**: Code review findings from `reviewer` agent use severity labels CRITICAL, MAJOR, MINOR. All CRITICAL and MAJOR issues must be resolved before merging. Fix using targeted coder tasks based on the review findings.

## 🔐 Pipeline Infrastructure

### Database (PostgreSQL via Supabase)

The pipeline tracks all operations in 8 PostgreSQL tables:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `pipeline_jobs` | Job queue with process lifecycle | status, progress, logs, pid, workflow_id, retry_count |
| `pipeline_runs` | Training/eval run metadata | status, loss, metrics, npc_key, technique |
| `pipeline_artifacts` | Generated artifacts (GGUFs, datasets) | artifact_type, file_path, checksum, size_bytes |
| `dataset_quality_gates` | DeepEval quality gate results | pass_rate, total/passed/failed, recommendation |
| `eval_sessions` | Evaluation session tracking | judge_model, win_rate, per_category_results |
| `pipeline_config_snapshots` | Frozen config at time of run | config_json, technique, preset, base_model |
| `api_keys` | API key management | key_hash, key_prefix, name, role, last_used_at |
| `api_audit_log` | Request audit trail | method, path, status_code, api_key_id, duration_ms |

**Connection:**
- Python scripts: `PipelineDB` auto-detects direct pg (`PIPELINE_DB_URL`) or Supabase REST (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`)
- TS backend: Uses `pg.Pool` via `src/backend/lib/db.ts`
- Local Supabase: `http://127.0.0.1:16437` (port may vary — check `supabase status`)

### Job Queue (PostgreSQL-backed, no Redis required)

The job queue at `src/backend/services/job-queue.ts` provides:

- **DB-persistent queue**: Jobs survive server restarts (backed by `pipeline_jobs` table)
- **Process lifecycle**: `spawn` with PID tracking, SIGTERM → 30s → SIGKILL escalation
- **Concurrency control**: Max concurrent jobs, per-startup PID recovery (checks `/proc/PID` liveness)
- **Polling**: `FOR UPDATE SKIP LOCKED` query (default 2s interval) with incremental stats counters
- **Retry**: Exponential backoff (2^n * 1s, max 5 attempts) for failed jobs
- **Graceful shutdown**: Drains running jobs before exit, 10s force-kill timeout

To swap to BullMQ (Redis), replace `JobQueue` with BullMQ's `Queue/Worker` — API-compatible.

### Auth System

The auth middleware at `src/backend/middleware/auth.ts` implements:

- **Bearer token auth**: `Authorization: Bearer <64-char-hex-key>` header validation
- **bcrypt hashing**: Keys hashed with bcrypt (cost 10) for constant-time comparison
- **Prefix-based lookup**: First 8 hex chars indexed for efficient key lookup
- **Three roles**: `admin` (full access), `operator` (manage jobs), `viewer` (read-only, write ops blocked)
- **Optional auth**: `optionalAuth` middleware for public-read endpoints

Bootstrap flow:
```bash
# Generate initial admin key (saves hash to DB, prints raw key to stdout)
python scripts/ops/setup_admin_key.py

# Use the key in all subsequent requests
curl -H "Authorization: Bearer <key>" http://localhost:3100/api/auth/keys
```

### Frontend Architecture

The dashboard uses a layered state architecture:

- **React Query** (`@tanstack/react-query`): Server state — 11 query hooks, 6 mutations, staleTime=5s, retry=2
- **Zustand**: UI-only state — active tab, filters, toasts, selection, sidebar state
- **WebSocket bridge** (`useWebSocketQuery.ts`): WS events invalidate React Query caches
- **Notifications**: `NotificationCenter` component with auto-dismiss (8s), type colors, badge count read state
- **Global search**: Ctrl+K modal searching across NPCs, datasets, runs, exports, jobs with localStorage recent searches
- **Keyboard shortcuts**: Input-aware shortcuts for navigation, search, refresh, stop-all

### Running in Modular Mode

```bash
# Development (Vite dev server + modular backend)
npm run dev:modular

# Production (serve built static files + modular backend)
npm run build
npm run start:modular

# Generate admin API key
python scripts/ops/setup_admin_key.py
```

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
- Notification center with toast system (bell icon, auto-dismiss, type-colored alerts)
- Ctrl+K global search across NPCs, datasets, runs, exports, jobs
- Keyboard shortcuts: Ctrl+K (search), Ctrl+S (stop jobs), Alt+1-4 (navigate tabs), Ctrl+R (refresh)
- Operations Matrix with pipeline control, W&B links, real-time job table
- Training Suite hyperparameter panel
- TensorBoard charts and W&B links
- GPU telemetry and system monitoring
- React Query for server state caching + Zustand for UI state

**Modular Server (dev):** `npm run dev:modular` starts the new modular backend at port 3100 with Vite dev middleware, rate limiting, auth, and job queue.
**Legacy Server:** `npm run dev` still starts the existing monolithic `server.ts` for backward compatibility.

## 🖥️ Active NPCs
| NPC | Key | Subject | Current local state |
|-----|-----|---------|---------------------|
| History Guide | `history_guide` | World history | Spec, reference doc, template dataset, exported LoRA GGUFs |
| Chef Assistant | `chef_assistant` | Culinary arts | Spec, reference doc, template dataset, exported LoRA GGUFs |
| Astronomy Guide | `astronomy_guide` | Astronomy and space science | Spec, reference doc, template dataset, exported LoRA GGUF |
| Fitness Coach | `fitness_coach` | Fitness, exercise science, and nutrition | Spec, reference doc, template dataset, exported LoRA GGUF |

Current local exports are adapter GGUFs under `exports/{npc_key}/`. Unity runtime should load the shared llama3.2 3B base model once and swap LoRA adapters plus the NPC system prompt while dialoguing with the local Supabase container.

---

## 📚 Key Reference Documents

| Document | Purpose |
|----------|---------|
| `docs/TRAINING_WORKFLOW_CONTEXT.md` | Full training pipeline detail — stages, presets, flags, data flow |
| `README.md` | Project overview and quick start |
| `AGENTS.md` | (this file) Quick-reference for AI agents |

---
*For detailed human-readable guides, see the [README.md](README.md) and the `docs/` directory.*
