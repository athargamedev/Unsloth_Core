# Frontend Control Dashboard

The Frontend Control Dashboard is the web control plane for Unsloth_Core training workflows. It provides:
- Pipeline orchestration for `./ucore` commands
- Deep observability (including externally started jobs)
- Resilient realtime updates via WebSocket-to-React-Query bridge
- Schema-driven command launch forms with validation
- Auth-protected API with role-based access control

## Architecture

```
Frontend (React + Vite + Tailwind)
    │
    ├── Zustand Store (UI state: tabs, filters, toasts, selection)
    ├── React Query (11 query hooks + 6 mutations, staleTime=5s)
    ├── WebSocket Bridge (useWebSocketQuery: invalidates query caches)
    └── Components (30+ components: TrainingSuite, OperationsMatrix, etc.)
    │
    ▼ HTTP / WebSocket
    │
Backend (Modular Express, port 3100)
    │
    ├── API Routes (12 route modules under /api/)
    ├── Auth Middleware (Bearer token, bcrypt, RBAC)
    ├── Audit Middleware (fire-and-forget to api_audit_log)
    ├── Job Queue (PostgreSQL, FOR UPDATE SKIP LOCKED)
    └── Registry (in-memory + filesystem artifact sync)
    │
    ▼
PostgreSQL (local Supabase, port 15434)
    ├── Pipeline Tables (jobs, runs, artifacts, etc.)
    └── Runtime Tables (npc_profiles, dialogue_sessions, etc.)
```

## Key Components

### State Management

Dashboard state is divided between two systems:

**React Query (Server State)** — 11 query hooks + 6 mutations:
- `useJobsQuery()` — Full job state snapshot, polls every 5s
- `useTelemetryQuery()` — GPU metrics, polls every 10s
- `useSystemStatusQuery()`, `useHealthCheckQuery()` — Backend health
- `useDatasetsQuery()`, `useSubjectListQuery()` — Dataset management
- `useRunArtifactsQuery()`, `useExportArtifactsQuery()` — Artifact listing
- `usePresetsQuery()` — Training presets
- `useQualitySummaryQuery()` — DeepEval quality results
- `usePipelineStateQuery()`, `useNpcStatusQuery()` — Pipeline state
- `useOllamaStatusQuery()`, `useOllamaModelsQuery()` — Ollama management
- `useSupabaseStatusQuery()`, `useSupabaseLeaderboardQuery()` — Supabase
- `useWatchLogsQuery()` — Filesystem log alerts

**Zustand (UI State)** — Persisted locally:
- Active tab, selected job IDs, filters
- Training config (spec, preset, technique, hyperparameters)
- Toast/notification queue (auto-dismiss, type-colored, read state)
- Global search recent queries (localStorage-persisted)
- Dataset view filter (NPC + technique)

### WebSocket Bridge

The `useWebSocketQuery` hook connects WebSocket events to React Query caches:
- `telemetry` events → `setQueryData` (no network round-trip)
- `job_update` events → `invalidateQueries` (triggers fresh fetch)
- `logs_cleared` events → invalidate log caches

This eliminates polling for telemetry (most latency-sensitive) and provides instant UI updates on job state changes.

### NotificationCenter

A bell-icon dropdown showing toast notifications:
- **Type-colored**: info (accent), success (green), warning (amber), error (red)
- **Auto-dismiss**: 8 seconds, with manual dismiss
- **Read state**: Unread badge count on bell icon
- **Clear all**: Mark all as read
- **Limit**: Shows latest 50 toasts

### GlobalSearch

Ctrl+K opens a modal search across 5 categories:
- **NPCs** (Hash icon), **Datasets** (Database icon), **Runs** (Cpu icon)
- **Exports** (Package icon), **Jobs** (Play icon)

Features:
- Keyboard navigation (arrow keys + Enter)
- Recent searches (localStorage-persisted, 20 item limit)
- Fetches all data on first open, caches for session
- Routes to relevant dashboard tab on selection

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Open global search |
| `Ctrl+S` | Stop all running jobs |
| `Alt+1-4` | Switch tabs |
| `Ctrl+R` | Refresh all data |
| `Escape` | Close modals/dropdowns |

All shortcuts are input-aware — they are ignored when an input/textarea/select is focused.

## API Endpoints

All endpoints are prefixed with `/api/`. Auth is required for all `/api/*` paths (enforced by `optionalAuth` middleware in `src/backend/index.ts`).

### Job & Pipeline Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/jobs` | required | Full job list (cache-refreshed) |
| `GET /api/jobs/state` | required | Jobs + workflow metadata snapshot |
| `GET /api/jobs/:id/logs` | required | Per-job log file tail |
| `POST /api/jobs/clear` | required | Clear all completed jobs |
| `POST /api/jobs/sync` | required | Force sync external artifacts |
| `POST /api/commands/start` | required | Start a command from the UI |
| `POST /api/pipeline` | required | Full pipeline orchestration |
| `POST /api/workflow` | required | Multi-step workflow chaining |

### Auth Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/auth/keys` | admin | List all API keys |
| `POST /api/auth/keys` | admin | Create new API key |
| `DELETE /api/auth/keys/:id` | admin | Revoke an API key |

### System Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/health` | none | Health check |
| `GET /api/telemetry` | required | GPU/system telemetry |
| `GET /api/events?since=<id>` | required | WebSocket event replay fallback |
| `GET /api/available-commands` | optional | List available CLI commands |
| `GET /api/command-schemas` | optional | Command payload schemas |

### Data Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/datasets` | optional | List generated datasets |
| `GET /api/exports` | required | List exported GGUFs |
| `POST /api/exports` | required | Export a trained model |
| `POST /api/training` | required | Launch a training run |
| `POST /api/eval` | required | Launch an evaluation |

### Infrastructure Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/ollama` | required | Ollama status and model list |
| `GET /api/supabase` | required | Supabase connection status |

## Dashboard Tabs

The main navigation provides these tabs:

1. **Training Suite** — Configure and launch training runs (spec, preset, technique, hyperparameters, W&B toggle)
2. **Operations Matrix** — Pipeline stage overview with job table, W&B links, per-NPC status
3. **Dataset Pipeline** — Generate, sanitize, and gate datasets with quality reports
4. **Eval Reports** — Side-by-side model evaluation results and HTML reports
5. **System Hub** — GPU telemetry, Supabase connection, Ollama management, health checks
6. **Feedback Loop** — Knowledge gap analysis and auto-retrain orchestration
7. **Colab Notebooks** — Integration with Google Colab-based training
8. **Leaderboard** — NPC evaluation scores across the 4 active NPCs

## Workflow Assistant

The dashboard includes a local Ollama-powered workflow assistant that provides contextual guidance without interfering with pipeline operations.

### Safety Architecture

The assistant is designed with **6 safety layers** to guarantee it never harms generation, training, or evaluation:

1. **Resource Guard** (`assistant-resource-guard.ts`): Blocks LLM calls when any GPU-heavy job is active (train, pipeline, dataset-eval, generate-ollama, export, evaluate, feedback). Falls back to deterministic state summaries.
2. **Immediate Unload** (`keep_alive: "0s"`): All config profiles tell Ollama to immediately unload the assistant model after each response, freeing VRAM for pipeline work.
3. **Shell Execution Blocked**: The `/api/assistant/execute` endpoint returns HTTP 403. Commands are "proposed" only — the user must launch them through the dashboard command modal.
4. **Read-Only Context**: The context collector reads filesystem and registry state but never writes. No pipeline artifacts are modified.
5. **System Prompt Boundaries**: Priority #1 in the system prompt explicitly prohibits concurrent GPU work.
6. **NPC Key Inference**: Uses snake_case pattern matching (requires underscore) to avoid phantom NPC key lookups from casual English words.

### Config Profiles

Three profiles in `workflow_assistant/assistant_config.json`:

| Profile | Model | Context | GPU Layers | Use Case |
|---------|-------|---------|------------|----------|
| `balanced_idle` (default) | `qwen3:latest` | 8192 | full | Normal operation when GPU is idle |
| `fast_safe` | `qwen2.5:3b` | 8192 | full | Lightweight queries |
| `cpu_fallback` | `qwen2.5:3b` | 4096 | 0 | CPU-only when GPU is fully occupied |

### Assistant API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/assistant/status` | GET | Model profile, resource state, mode (ready/paused) |
| `/api/assistant/chat` | POST | Chat with context-aware LLM (or deterministic fallback) |
| `/api/assistant` | POST | Backward-compatible alias for chat |
| `/api/assistant/load` | POST | Pre-warm the assistant model (blocked during GPU-heavy jobs) |
| `/api/assistant/unload` | POST | Unload the assistant model to free VRAM |
| `/api/assistant/execute` | POST | **Always returns 403** — shell execution disabled |

### Data Validation

All dashboard panels use Zod runtime schema validation integrated into React Query `queryFn` hooks. API responses are parsed through Zod schemas before reaching components, preventing silent crashes from malformed backend data. Panels using this pattern:

- `EvalReportsPanel.tsx` — Gold standard reference implementation
- `FeedbackLoopPanel.tsx` — Feedback result and gap schemas
- `EvalWorkflowPanel.tsx` — Eval report schemas with `refetchInterval` polling
- `DatasetPipelinePanel.tsx` — Quality summary and failure schemas

## Job Queue Integration

The dashboard manages jobs through the PostgreSQL-backed `JobQueue` class:
- Jobs survive server restarts
- Process lifecycle managed with PID tracking (SIGTERM → SIGKILL)
- Exponential backoff retry (2^n * 1s, max 5 attempts)
- Concurrent job limit configurable (default: 2 on RTX 3060)
- Stats tracked incrementally (full recount every 50 transitions)

The `JobQueue` and the in-memory `Registry` coexist — the registry tracks legacy and filesystem-discovered jobs; the job queue is the authoritative source for newly created jobs.

## Running the Dashboard

```bash
# Development (Vite dev server + modular backend)
cd frontend_control/unity-npc-llm-training-dashboard
npm run dev
# → http://localhost:3100

# Production (serve built static files)
npm run build
npm run start:modular

# Bootstrap auth
python scripts/ops/setup_admin_key.py
```

### Environment Variables

```env
PORT=3100
DATABASE_URL=postgresql://postgres:postgres@localhost:15434/postgres
GEMINI_API_KEY=your_key_here
```

## Notes

- All `/api/*` requests require a valid Bearer token (except `/api/health` and public-read endpoints)
- Bootstrap the first admin key with `python scripts/ops/setup_admin_key.py`
- If GPU telemetry is empty, verify `nvidia-smi` is available in PATH
- If ports are in use, stop duplicate server instances before restart
- Dashboard coexists with terminal-driven workflows — external work appears via sync/artifact discovery
- The modular backend (`npm run dev`) replaces the legacy `server.ts`; run `npm run start:modular` for production
