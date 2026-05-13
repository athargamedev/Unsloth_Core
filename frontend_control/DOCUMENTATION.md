# Unity NPC LLM Training Dashboard (MVP Integration)

## Architecture
- **Frontend**: `frontend_control/unity-npc-llm-training-dashboard/src/App.tsx` (single-page dashboard with tabs).
- **Backend**: `frontend_control/unity-npc-llm-training-dashboard/server.ts` (Express + Vite middleware).
- **Runtime state**: persisted to `frontend_control/unity-npc-llm-training-dashboard/.runtime/registry.json`.
- **Data sources**:
  - `datasets/` for dataset inventory
  - `subjects/` for subject specs
  - `outputs/` for run directories
  - `exports/` for GGUF artifacts

## Execution Modes
- `local` (implemented): starts jobs with `spawn(...)` in repository root and streams stdout/stderr.
- `remote` (scaffold): API contract exists, but starting commands returns `501 not implemented`.

Mode endpoints:
- `GET /api/execution-mode`
- `POST /api/execution-mode` with `{ "mode": "local" | "remote" }`

## API Endpoint Reference
- `GET /api/jobs` → persisted job registry
- `GET /api/logs` → global rolling logs
- `GET /api/datasets` → canonical dataset view by `datasets/{npc_key}/{technique}`
- `GET /api/analytics?jobId=...` → analytics points parsed from selected job logs
- `GET /api/available-commands` → allowed operations and UI metadata
- `POST /api/assistant` → server-side Gemini proxy (uses `GEMINI_API_KEY` from server env)
- `POST /api/commands/start` → start command by `commandId` and validated payload
- `POST /api/commands/stop` → stop running job by id
- `GET /api/runs` → run folders under `outputs/`
- `GET /api/exports` → exported GGUF files
- `GET /api/system/status` → mode + running/total job counters
- `GET /api/subjects` → available `subjects/*.json`

## UI Action → Command Mapping
- **Training tab / Launch Training Cluster** → `commandId: train` (`./ucore train <spec> --preset <preset>`)
- **Dataset tab / Generate from Spec** → `commandId: dataset-generate` (`./ucore generate <spec>`)
- **Right sidebar / Run Dataset Generator** → `dataset-generate`
- **Right sidebar / Initialize LoRA Train** → `train`
- **Right sidebar / Export for Unity** → `export`
- **System Hub cards** → `available-commands` allowlist entries (same backend contract)
- **Overview row Stop action** → `POST /api/commands/stop`

## Safety Model
- All executable commands are backend-allowlisted.
- Path-bearing fields (`spec`, `datasetPath`, `modelPath`, `baseline`, `candidate`, optional `valData` and `unityProject`) are resolved against repository root and constrained to allowed roots (`subjects/`, `datasets/`, `exports/`, `outputs/`, repo root for `unityProject`).
- Any path escaping allowed roots is rejected with HTTP 400 and a clear error.
- Command schemas expose `requiredFields`, and backend + frontend both enforce required arguments before execution.
- Backend never executes arbitrary shell strings.
- Process execution uses argument arrays with `shell: false`.

## Job Lifecycle Notes
- On server startup, persisted `running` / `pending` jobs are reconciled to `failed` with `terminalReason: server_restarted` and `finishedAt` set.
- Manual stop requests now return `status: stop_requested` and set `stopRequested=true`; terminal state is finalized only from child `close` events (`stopped` when stop was requested, otherwise normal exit mapping).
- Stop flow includes escalation: if a process does not exit after `SIGTERM`, server sends `SIGKILL` after the timeout window to prevent orphaned runners.
- Stage-level logs are populated continuously as stdout/stderr lines stream.

## Current Remote Limitations
- `remote` execution mode remains scaffolded only.
- `POST /api/commands/start` returns `501` in remote mode; there is no remote scheduler/worker handoff yet.

## Local Run & Build
From `frontend_control/unity-npc-llm-training-dashboard`:

```bash
npm install
npm run dev
```

Verification/build:

```bash
npm run lint
npm run build
```
