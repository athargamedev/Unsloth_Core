# Unsloth_Core

A professional, "agent-first" pipeline for building the best GGUF LoRA adapters for the `llama-3.2-3b-instruct` base model, so Unity NPCs can load at runtime in LLMUnity and manage dialogue sessions through local Supabase.

## North Star

- Train and export high-quality LoRA adapters as GGUF for `llama-3.2-3b-instruct`.
- Load those adapters in Unity through the LLMUnity plugin at runtime.
- Support persistent NPC dialogue sessions backed by the local Supabase container.
- Keep dataset generation, DeepEval gating, training, export, and runtime integration aligned to that deployment target.

## Quick Start

```bash
# 1. Start the modular backend (port 3100)
npm run dev

# 2. Activate the Python environment
source unsloth_env/bin/activate

# 3. Verify everything is ready
./ucore audit check
```

## Full Pipeline

The pipeline transforms an NPC subject spec into a deployable GGUF LoRA adapter in 7 stages:

```bash
# 1. Validate generation readiness
./ucore validate-spec subjects/NPC_specs/history_guide.json --generation-ready

# 2. Generate dataset (template, docs, or ollama technique)
./ucore generate subjects/NPC_specs/history_guide.json --technique template

# 3. Sanitize and validate ChatML format
./ucore sanitize subjects/datasets/history_guide/template/train.jsonl \
  --output subjects/datasets/history_guide/template/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

# 4. DeepEval quality gate (uses qwen3:latest judge)
./ucore dataset-eval subjects/NPC_specs/history_guide.json \
  --technique template --judge-model qwen3:latest

# 5. Train LoRA adapter
./ucore train subjects/NPC_specs/history_guide.json \
  --technique template --preset fast-3b --export-gguf

# 6. Smoke test the exported adapter
./ucore smoke exports/history_guide/history_guide-lora-f16.gguf

# 7. Full evaluation vs baseline
./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf \
  --spec subjects/NPC_specs/history_guide.json --report-html
```

## Infrastructure

### Modular Backend
`npm run dev` starts the Express dashboard at **port 3100** with:
- **Auth**: Bearer token API keys (bcrypt hashed, prefix-indexed lookup)
- **Job queue**: PostgreSQL-backed with `FOR UPDATE SKIP LOCKED` polling, PID tracking, retry with exponential backoff
- **Audit logging**: All mutations logged to `api_audit_log` with sensitive field redaction

### Supabase
The local Supabase instance manages two schema domains:
- **Runtime tables** (port 15434 Postgres, 16437 Kong API): `npc_profiles`, `dialogue_sessions`, `npc_memories` for Unity NPC runtime
- **Pipeline tables** (same Postgres): `pipeline_jobs`, `pipeline_runs`, `pipeline_artifacts`, `dataset_quality_gates`, `eval_sessions`, `pipeline_config_snapshots`, `api_keys`, `api_audit_log`

### Pipeline DB
Python pipeline scripts auto-connect to Supabase via the `PipelineDB` class (`scripts/ops/pipeline_db.py`):
- Direct mode: `psycopg2` via `SUPABASE_DB_URL` or `PIPELINE_DB_URL`
- REST mode: Supabase REST API via `SUPABASE_URL` + `SUPABASE_KEY`
- Fallback: localhost `127.0.0.1:15434`
- **Best-effort**: All DB writes are wrapped in try/except — never block the pipeline

### Auth
API key authentication with bcrypt-hashed 64-char hex keys:
```bash
# Bootstrap the first admin key
python scripts/ops/setup_admin_key.py

# Use the key for all API requests
curl -H "Authorization: Bearer <key>" http://localhost:3100/api/jobs
```

## Dashboard

The React frontend provides full pipeline visibility:

| Tab | Purpose |
|-----|---------|
| Training Suite | Configure and launch training runs |
| Operations Matrix | Pipeline control, job table, W&B links |
| Dataset Pipeline | Generate, sanitize, and gate datasets |
| Eval | Side-by-side model evaluation and reports |
| System Hub | GPU telemetry, Supabase status, Ollama management |
| Feedback Loop | Gap analysis and auto-retrain |
| Colab Notebooks | Integration with Google Colab |

Key UI features:
- **NotificationCenter**: Bell-icon toast system with type-colored alerts and auto-dismiss
- **GlobalSearch**: Ctrl+K to search across NPCs, datasets, runs, exports, and jobs
- **Keyboard shortcuts**: Ctrl+K (search), Ctrl+S (stop jobs), Alt+1-4 (tabs), Ctrl+R (refresh)
- **State management**: Zustand for UI state, React Query (11 queries + 6 mutations) for server state, WebSocket bridge for real-time updates

## Active NPCs

| NPC | Key | Subject | Export State |
|-----|-----|---------|-------------|
| History Guide | `history_guide` | World history | LoRA GGUF exported |
| Chef Assistant | `chef_assistant` | Culinary arts | LoRA GGUF exported |
| Astronomy Guide | `astronomy_guide` | Astronomy and space science | LoRA GGUF exported |
| Fitness Coach | `fitness_coach` | Fitness, exercise science, and nutrition | LoRA GGUF exported |

## GGUF Naming Conventions

- **Adapter mode**: `{npc_key}-lora-f16.gguf` (MBs, loaded via `llama-server --lora`)
- **Full-merge**: `{npc_key}-{model_short}-{quant}.gguf` (GBs, standalone, default quant `q4_k_m`)

## Project Structure

```
ucore                     — Unified CLI entry point
scripts/                  — Pipeline Python scripts
  dataset/                — Generation and sanitization
  training/               — Unsloth SFTTrainer with LoRA
  evaluation/             — Model evaluation and reporting
  export/                 — GGUF export and batch export
  ops/                    — Pipeline DB, hooks, auth bootstrap
frontend_control/         — Dashboard (React + Express)
  unity-npc-llm-training-dashboard/
    src/backend/          — Modular Express backend (27 files)
      routes/             — 12 route modules
      services/           — Job queue, runner, registry, telemetry
      middleware/          — Auth, audit, security, validation
      lib/                — DB pool, logger, path utils
    src/components/       — 30 React components
    src/hooks/            — React Query + WebSocket hooks
    src/stores/           — Zustand app store
subjects/                 — NPC specs, datasets, reference docs
supabase/migrations/      — 8 migration files
configs/                  — YAML presets for training
exports/                  — GGUF LoRA adapters for Unity
outputs/                  — Training checkpoints and logs
docs/                     — Full documentation suite
```

## Documentation

- **[AGENTS.md](AGENTS.md)**: Primary reference for AI assistants
- **[docs/MAP.md](docs/MAP.md)**: Central index of all technical documentation
- **[docs/architecture/PIPELINE_FLOW.md](docs/architecture/PIPELINE_FLOW.md)**: 7-stage pipeline flow
- **[docs/architecture/SUPABASE_SCHEMA.md](docs/architecture/SUPABASE_SCHEMA.md)**: Database schema (runtime + pipeline)
- **[docs/architecture/MODULAR_BACKEND.md](docs/architecture/MODULAR_BACKEND.md)**: Express backend design
- **[docs/architecture/AUTH_SYSTEM.md](docs/architecture/AUTH_SYSTEM.md)**: API key auth system
- **[docs/architecture/JOB_QUEUE.md](docs/architecture/JOB_QUEUE.md)**: PostgreSQL-backed job queue
- **[docs/architecture/PIPELINE_DB.md](docs/architecture/PIPELINE_DB.md)**: Python database integration
- **[docs/integration/FRONTEND_DASHBOARD.md](docs/integration/FRONTEND_DASHBOARD.md)**: Dashboard architecture
- **[docs/reference/CLI_REFERENCE.md](docs/reference/CLI_REFERENCE.md)**: Full `./ucore` command reference
- **[docs/reference/SUBJECT_SPEC.md](docs/reference/SUBJECT_SPEC.md)**: NPC spec schema

## License

MIT. See [LICENSE](LICENSE) for details.
