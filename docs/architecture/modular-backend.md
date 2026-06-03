# Modular Backend Architecture

## Overview

The modular backend replaces the original monolithic `server.ts` (4,495 lines) with 27 files organized by concern. It lives under `src/dashboard/unity-npc-llm-training-dashboard/src/backend/` and provides auth, job queue, audit logging, and all API routes for the dashboard.

```
src/backend/
├── index.ts                  — App factory: mounts middleware + 12 route modules
├── types.ts                  — TypeScript interfaces (QueueJob, Registry, Telemetry, etc.)
├── routes/                   — 12 route handler modules
│   ├── auth.ts               — GET/POST/DELETE /api/auth/keys
│   ├── jobs.ts               — GET /api/jobs, POST /api/jobs/sync, etc.
│   ├── pipeline.ts           — POST /api/pipeline
│   ├── datasets.ts           — GET /api/datasets
│   ├── eval.ts               — POST /api/eval
│   ├── export.ts             — GET/POST /api/exports
│   ├── training.ts           — POST /api/training
│   ├── system.ts             — GET /api/health, /api/telemetry, /api/system/status
│   ├── ollama.ts             — GET /api/ollama
│   ├── supabase.ts           — GET /api/supabase
│   ├── commands.ts           — GET /api/available-commands, /api/command-schemas
│   └── workflow.ts           — POST /api/workflow
├── services/                 — 8 business-logic modules
│   ├── job-queue.ts          — PostgreSQL-backed JobQueue class
│   ├── queue-worker.ts       — Process spawning, log flushing, PID tracking
│   ├── job-runner.ts         — Launch/stop jobs, stage management
│   ├── registry.ts           — Registry persistence, external sync, process discovery
│   ├── command-builder.ts    — CLI command definitions and payload builders
│   ├── artifact-scanner.ts   — Filesystem artifact discovery
│   ├── telemetry.ts          — GPU telemetry (nvidia-smi), system metrics
│   └── model-detector.ts     — Local model (llama-server / Ollama) detection
├── middleware/               — 4 middleware modules
│   ├── auth.ts               — Bearer token auth, requireRole, optionalAuth
│   ├── audit.ts              — Fire-and-forget audit logging to api_audit_log
│   ├── security.ts           — Path traversal protection, rate limiting, JSON body parser
│   └── validation.ts         — Request body validation helpers
└── lib/                      — 5 shared utility modules
    ├── db.ts                 — pg.Pool singleton, query(), healthCheck(), closePool()
    ├── logger.ts             — Structured logging
    ├── path-utils.ts         — Repo root discovery, path resolution
    ├── read-job-logs.ts      — Per-job log file tailing
    └── validation.ts         — Schema validation utilities
```

## Route Map

All endpoints are prefixed with `/api/` and registered on an Express sub-app. Auth is required for all `/api/*` paths (enforced in `index.ts`), but routes can opt into optional auth for public-read endpoints.

| Prefix | Endpoints | Auth | Description |
|--------|-----------|------|-------------|
| `/api/auth/keys` | GET, POST, DELETE | admin | API key management (list, create, revoke) |
| `/api/jobs` | GET, POST, DELETE, PATCH | required | Job queue CRUD, state, logs, sync, clear |
| `/api/system` | GET | required | System status, GPU telemetry, health |
| `/api/training` | POST | required | Launch training runs |
| `/api/eval` | POST | required | Launch model evaluations |
| `/api/datasets` | GET | optional | List generated datasets |
| `/api/exports` | GET, POST | required | List and export GGUF artifacts |
| `/api/pipeline` | POST | required | Full pipeline orchestration |
| `/api/workflow` | POST | required | Multi-step workflow chaining |
| `/api/ollama` | GET | required | Ollama model management |
| `/api/supabase` | GET | required | Supabase connection status |
| `/api/commands` | GET | optional | Available commands and command schemas |

## Middleware Pipeline

Request processing order in `createApp()` (`src/backend/index.ts`):

1. **`pathTraversalMiddleware`** — Blocks `..` and URL-encoded `%2e` path traversal attempts
2. **`auditLog`** — Fire-and-forget logging to `api_audit_log` on response finish. Logs mutations (POST/PUT/PATCH/DELETE) and all errors (>=400). GETs with <400 are skipped
3. **`optionalAuth`** — Reads Bearer token from Authorization header. If valid, sets `req.apiKey`. Does NOT fail on missing token — validates only if header is present
4. **`jsonBodyParser`** — Standard `express.json()` with 1MB limit
5. **`rateLimitMiddleware`** — Optional, commented out by default. Enable in production: 100 req/min window

Route handlers then apply additional auth gates:
- **`requireRole("admin")`** on auth and sensitive operations
- **`requireRole("admin", "operator")`** on mutation endpoints
- **Viewer role** blocked on all POST/PUT/PATCH/DELETE

## Key Design Decisions

### Absolute Paths
All routes use absolute paths (`/api/...`), registered on the Express app directly. No nested routers or path prefixes — keeps URL resolution simple and grep-friendly.

### Shared Database Pool
A single `pg.Pool` singleton (managed in `lib/db.ts`) serves all routes. Pool configuration auto-detects from `DATABASE_URL`, `SUPABASE_DB_URL`, or falls back to local Supabase defaults (`127.0.0.1:15434`).

### Request Augmentation
The `apiKey` field is added to the Express `Request` type via TypeScript declaration merging in `auth.ts`, so all route handlers can access authenticated user info type-safely.

### Separation of Concerns
- **Routes** handle HTTP (parse request, format response, return status codes)
- **Services** contain business logic (job lifecycle, registry management, GPU polling)
- **Middleware** implements cross-cutting concerns (auth, audit, security)
- **Lib** provides shared utilities (DB, logging, I/O)

### No WebSocket in Modular
The modular backend does not include a WebSocket layer. The `broadcast()` function is a no-op placeholder — WebSocket broadcasting can be added later by implementing a WS server around the Job Queue's `onUpdate` callbacks.

### Dual Registry
The modular backend maintains both the in-memory `registry.json` (for backward compatibility) and the `pipeline_jobs` DB table (for persistence). The JobQueue class is the authoritative state source for new jobs; the registry tracks legacy jobs and filesystem artifacts.

## Startup

The modular backend is started via `server.ts` at the dashboard root:

```typescript
import { createApp } from "./src/backend/index";
// ... creates Registry, JobQueue, commandMap ...
const app = createApp({ registry, commandMap, repoRoot, ... });
app.listen(PORT);
```

Run with:
```bash
npm run dev        # Development (Vite dev middleware + modular backend)
npm run start:modular  # Production (serves built static files)
```
