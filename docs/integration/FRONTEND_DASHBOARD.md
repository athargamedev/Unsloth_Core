# Frontend Control Dashboard

The Frontend Control Dashboard is the web control plane for Unsloth_Core training workflows.
It provides:
- reliable process orchestration for `./ucore` commands,
- deep observability (including externally started jobs),
- resilient realtime updates over WebSocket,
- schema-driven command launch forms with validation,
- deterministic stage/progress behavior.

## Architecture

- Frontend: React + Vite + Tailwind.
- Backend: Express (`frontend_control/unity-npc-llm-training-dashboard/server.ts`).
- Process runtime: local child-process runner for `./ucore` / scripts.
- State persistence: `.runtime/registry.json`.
- Realtime channel: WebSocket with event IDs, replay support, and heartbeat.

## Major Reliability Improvements

### 1) Full workflow observability (internal + external)

The dashboard no longer relies only on jobs started from UI.

It now merges 3 truth sources:
1. Internal runner jobs (started via `/api/commands/start` and workflow APIs).
2. Filesystem artifacts (completed external work discovered from `subjects/datasets/`, `outputs/`, `exports/`).
3. Active OS process discovery (`ps` scan for relevant `ucore` / pipeline scripts).

External jobs are imported/detected with stable IDs like:
- `ext_dataset_<npc>_<technique>`
- `ext_train_<npc>_<runid>`
- `ext_proc_<pid>`

This allows users to see work started from terminal/other tools directly in dashboard views.

### 2) WebSocket replay + heartbeat resilience

Realtime sync now includes:
- monotonic `eventId` on outbound websocket events,
- in-memory replay buffer on server,
- client reconnect replay requests (`request_replay`),
- heartbeat ping/pong to detect stale sockets,
- HTTP replay fallback: `GET /api/events?since=<eventId>`.

Result: transient disconnects no longer silently desync job state.

### 3) Schema-driven command launch surface

Command forms are now generated from backend schemas instead of hardcoded UI fields.

Backend endpoint:
- `GET /api/command-schemas`

Schema includes:
- field type (`string|number|boolean`),
- required flag,
- default value,
- enum options,
- descriptions.

Frontend behavior:
- builds nested payloads from dotted paths (e.g. `options.technique`),
- type-casts user input by schema type,
- blocks execution when required fields are missing.

Result: launch UX stays in lockstep with backend command contracts.

### 4) Deterministic stage/progress truth model

Progress is no longer heuristic bucketed percentages.

Current behavior:
- stage statuses are derived from command + runtime truth,
- progress is computed from stage-state truth only,
- completed jobs = 100,
- in-flight/terminal non-complete jobs get deterministic stage-based progress.

Implementation is extracted for testability:
- `progressTruth.ts`
  - `deriveStageStatuses(...)`
  - `computeProgressFromStages(...)`

## API Endpoints Added/Upgraded

Core jobs + sync:
- `GET /api/jobs` (includes sync of artifacts + active process discovery before response)
- `POST /api/jobs/sync` (manual artifact/process sync)
- `GET /api/processes/discover` (manual active external process discovery)

Realtime/state recovery:
- `GET /api/events?since=<eventId>`
- websocket replay request/response protocol (`request_replay`)

Command intelligence:
- `GET /api/available-commands`
- `GET /api/command-schemas`

## Logging and Persistence

- Per-job logs are capped and persisted.
- Stage logs are capped separately.
- Global log stream is transient and reset on restart.
- Registry persistence is debounced during heavy output and flushed on terminal events.

## Test Coverage Added

Unit tests:
- `progressTruth.test.ts`
  - stage derivation correctness,
  - progress computation for running/stopped/completed/pending.

Integration tests:
- `api.jobs.integration.test.ts`
  - `/api/jobs` shows stage-derived progress for live job,
  - stop lifecycle verifies `running -> stopped` plus stopped stage marking.

NPM scripts:
- `npm run lint`
- `npm run test`
- `npm run test:unit`
- `npm run test:integration`

## Runbook

From `frontend_control/unity-npc-llm-training-dashboard`:

```bash
npm install
npm run lint
npm run test
npm run dev
```

Default URL: `http://localhost:3100`

Optional `.env`:

```env
PORT=3100
GEMINI_API_KEY=your_key_here
```

## Notes

- If GPU telemetry is empty, verify `nvidia-smi` is available in PATH.
- If ports are already in use, stop duplicate dashboard server instances before restart.
- Dashboard is designed to coexist with terminal-driven workflows; external work should appear via sync/discovery.
