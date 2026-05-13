# Unity NPC LLM Training Dashboard

Web control plane for Unsloth_Core workflow execution, observability, and realtime monitoring.

Main technical guide:
- ../../docs/integration/FRONTEND_DASHBOARD.md

## What this dashboard now guarantees

- Visibility of dashboard-started jobs and externally-started CLI jobs.
- WebSocket resilience with replay and heartbeat handling.
- Schema-driven command forms with required-field validation.
- Deterministic stage/progress behavior (no heuristic progress buckets).
- Unit + integration tests for workflow truth and lifecycle transitions.

## Quick Start

From this directory:

```bash
npm install
npm run lint
npm run test
npm run dev
```

Open:
- http://localhost:3100

## Environment

Create `.env` (or export vars):

```env
PORT=3100
GEMINI_API_KEY=your_key_here
```

## Useful API endpoints

- GET `/api/jobs`
- POST `/api/jobs/sync`
- GET `/api/processes/discover`
- GET `/api/events?since=<eventId>`
- GET `/api/available-commands`
- GET `/api/command-schemas`

## Test Commands

- `npm run test` — all tests
- `npm run test:unit` — `progressTruth.test.ts`
- `npm run test:integration` — API integration tests

## Files to know

- `server.ts` — backend runtime, APIs, websocket, orchestration
- `src/hooks/useWebSocket.ts` — reconnect/replay handling
- `src/App.tsx` — schema-driven command UI + validation
- `progressTruth.ts` — stage/progress truth logic
- `progressTruth.test.ts` — unit tests
- `api.jobs.integration.test.ts` — integration tests
