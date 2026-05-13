# Frontend Integration Handoff — Unity NPC LLM Training Dashboard

## 1) Purpose and scope
This document hands off the completed integration for:

- **Frontend app**: `frontend_control/unity-npc-llm-training-dashboard` (React + Vite)
- **Backend API/runtime**: `frontend_control/unity-npc-llm-training-dashboard/server.ts` (Express + local process runner)
- **Pipeline bridge**: local command execution into repo-root `./ucore` and selected script calls

Scope covers what is implemented now, how to run/operate it, and where the guardrails are.

---

## 2) Final architecture

### Frontend
- Single-page React app (`src/App.tsx`)
- Polls backend every 5s for jobs/logs/status/commands/datasets/subjects
- Executes operations through backend APIs only (no direct shell from browser)

### Backend
- Express server in `server.ts`
- Hosts API routes + Vite middleware (dev) or static `dist` (prod)
- Spawns local child processes for commands when execution mode is `local`

### Runtime registry
- Persistent state in:
  - `frontend_control/unity-npc-llm-training-dashboard/.runtime/registry.json`
- Stores:
  - `executionMode` (`local` or `remote`)
  - job history/status/progress/stage logs
  - global log stream (capped)
- On server restart, any `pending/running` jobs are reconciled to `failed` with `terminalReason=server_restarted`

### ucore integration
Primary command path is repo-root `./ucore` with validated arguments:

- `generate`, `sanitize`, `train`, `pipeline`, `export`, `export-adapter`, `evaluate`, `smoke`, `supabase-check`
- One deploy command currently uses `python scripts/export.py ...` (explicitly implemented that way)

---

## 3) Execution modes

### Local mode (implemented)
- `/api/commands/start` builds a command and spawns it in repo root (`cwd=../../` from dashboard)
- Stdout/stderr are streamed into job logs + global logs

### Remote mode (scaffold contract only)
- API supports `GET/POST /api/execution-mode`
- If mode is `remote`, start returns **501** with:
  - `{"error":"Remote runner not implemented yet.","mode":"remote"}`
- UI can display REMOTE/LOCAL state, but remote execution backend is intentionally not wired yet.

---

## 4) Endpoint quick reference

## Job + command execution
- `GET /api/available-commands` — command catalog including `requiredFields`
- `POST /api/commands/start` — start a command job
- `POST /api/commands/stop` — graceful stop request (see semantics below)
- `GET /api/jobs` — job list + statuses
- `GET /api/logs` — global logs
- `GET /api/analytics?jobId=<id>` — derived chart points from job log loss lines

## Data inventory
- `GET /api/datasets`
- `GET /api/subjects`
- `GET /api/runs`
- `GET /api/exports`

## Runtime/system state
- `GET /api/system/status`
- `GET /api/execution-mode`
- `POST /api/execution-mode` with `{ "mode": "local" | "remote" }`

## Assistant
- `POST /api/assistant` with `{ message, history }`
  - No `GEMINI_API_KEY`: returns a non-failing informational response
  - Upstream timeout: hard abort at 15s, returns HTTP **504** and `{ timeout: true }`

---

## 5) UI action → backend command mapping

| UI action | API payload (`commandId`) | Backend command |
|---|---|---|
| Generate from Spec / Run Dataset Generator | `dataset-generate` + `spec` | `./ucore generate <spec>` |
| Sanitize Dataset (System Hub) | `dataset-sanitize` + `options.datasetPath` | `./ucore sanitize <datasetPath>` |
| Launch Training Cluster / Initialize LoRA Train | `train` + `spec` (+ optional `preset`) | `./ucore train <spec> [--preset <preset>]` |
| Run Full Pipeline | `pipeline` + `spec` | `./ucore pipeline <spec>` |
| Export for Unity | `export` + `npcKey` + `options.modelId` | `./ucore export <npcKey> --model <modelId>` |
| Export Adapter | `export-adapter` + `npcKey` | `./ucore export-adapter outputs/<npcKey>/` |
| Evaluate Candidate | `evaluate` + `spec` + `options.baseline` + `options.candidate` (+ optional `valData`, `unityProject`) | `./ucore evaluate --baseline <...> --candidate <...> --spec <...> [--val-data <...>] [--unity-project <...>]` |
| Smoke Test | `smoke` + `spec` + `options.modelPath` | `./ucore smoke <modelPath> --spec <spec>` |
| Deploy Package (System Hub) | `deploy` + `options.npcKey` + `options.modelId` | `python scripts/export.py <npcKey> --model <modelId>` |
| Supabase Health Check | `supabase-check` | `./ucore supabase-check` |

**requiredFields contract**: frontend reads `requiredFields` from `/api/available-commands`; if a required field is missing, it prompts the user and sends the completed payload. Backend enforces required fields again server-side.

---

## 6) Operational runbook

All commands below are run from:
`/home/athar/Projects/Unsloth_Core/frontend_control/unity-npc-llm-training-dashboard`

### Start dev server
```bash
npm install
npm run dev
```
Server starts at `http://localhost:3100` (Express + Vite middleware + WebSocket).

### Build for production
```bash
npm run build
```
Outputs frontend + bundled server into `dist/` (`dist/server.cjs`).

### Run production build
```bash
npm run start
```

### Stop/reset stuck jobs
1. Use `POST /api/commands/stop` (UI stop action) with job `id`.
2. Implemented semantics:
   - immediate `SIGTERM`
   - response returns `{"status":"stop_requested","id":"..."}`
   - if still alive after 10s, escalates to `SIGKILL`
3. Job terminal status is set to `stopped` with `terminalReason=user_requested_stop` once process closes.

### Where logs/registry live
- Runtime registry and persisted logs:
  - `frontend_control/unity-npc-llm-training-dashboard/.runtime/registry.json`
- Per-job recent logs are embedded in job objects in that registry.

---

## 7) Security model summary

- **No browser shell access**: all execution is brokered through backend route handlers.
- **Command allowlist**: only known `commandId` definitions are executable.
- **Input validation**:
  - required field enforcement (`requiredFields`)
  - token sanitization for IDs/options (restricted character set)
  - canonical path resolution from nearest existing parent
  - path must remain inside explicit allowed roots (subjects/datasets/exports/outputs/repo root for unity project)
- **Traversal/symlink hardening**: canonicalization (`realpath`) + root containment check prevents escaping allowed directories.

---

## 8) Known limitations and recommended enhancements

### Current limitations
- Remote execution mode is API-level scaffold only (501 on start).
- Process state exists in local JSON registry (single-node, no locking/distributed orchestration).
- Assistant is single-provider and request-timeout bounded at 15s.

### Recommended next enhancements
1. Implement remote runner adapter behind existing `executionMode` contract.
2. Add authenticated access and role-based command permissions.
3. Add structured per-job log files (in addition to registry snapshot) for long runs.
4. Add resumable/retry semantics for interrupted pipeline steps.
5. Expand command schema with typed options (instead of prompt-based required-field input).

---

## 9) First day checklist (new teammate)

1. Open `server.ts` and `src/App.tsx` to understand command contract + UI trigger flow.
2. Run `npm install && npm run dev` in the dashboard directory.
3. Confirm health endpoints:
   - `/api/system/status`
   - `/api/available-commands`
   - `/api/subjects`
4. Trigger one safe command (`supabase-check` or dataset generate on a known spec).
5. Stop that job once to validate stop behavior (`stop_requested`, SIGTERM, possible SIGKILL escalation).
6. Inspect `.runtime/registry.json` after a run and after a restart (orphan reconciliation behavior).
7. Verify assistant behavior in both cases:
   - without `GEMINI_API_KEY` (graceful message)
   - with key + timeout handling awareness (15s/504 path)
8. Review allowed path roots before adding any new command requiring file inputs.

This integration is complete and approved for team use in **local mode**.

---

## 10) FastAPI Dashboard Deprecation

### Status: DEPRECATED

The legacy FastAPI dashboard at `scripts/dashboard.py` (port 8000) is **deprecated**.

### What changed
All functionality previously provided by the FastAPI dashboard has been migrated to the React+Express SPA:

| FastAPI Feature | SPA Equivalent |
|----------------|----------------|
| Real-time metrics (WebSocket) | WebSocket at `/ws` in Express |
| Training config browser | Training Suite tab |
| Dataset viewer | Dataset Factory tab |
| Eval reports | System Hub → Eval Reports |
| Model comparison | Model Comparison tab |
| System telemetry | System Hub tab |

### Migration timeline
- **Now**: FastAPI still runs on port 8000 with deprecation headers (`X-Deprecated: true`)
- **Next release**: FastAPI will be removed; all functionality is in the Express SPA on port 3100

### To stop FastAPI
```bash
# Find and kill the process
pkill -f "python scripts/dashboard.py"
# Or
kill $(lsof -ti:8000)
```

### Icons/Visual markers
- Running dashboard.py will log: `WARNING  Deprecated FastAPI dashboard called: GET / — use React+Express SPA`
- All API responses include header: `X-Deprecated: true`
