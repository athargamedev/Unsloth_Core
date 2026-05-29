# frontend_control/unity-npc-llm-training-dashboard/ AGENTS

## Purpose
This folder contains the dashboard backend and frontend code that orchestrate jobs, evaluation, reports, and live state.

## Rules
- Treat the backend command builder in `server.ts` as the source of truth for CLI flag wiring.
- Keep frontend forms, payloads, and server command schemas in sync.
- Eval reporting must preserve HTML report generation, tracking, judge mode, judge model, base model, LoRA weight, question count, and feedback JSON support.
- Prefer backend-owned state over frontend inference for jobs, reports, and progress.
- When changing paths or defaults, verify both the API shape and the rendered UI.
- Keep compatibility with existing `./ucore` commands and the categorized script paths.

## Quick checks
- `npm run build`
- Verify `/api/jobs/state` and `/api/eval-reports` return the expected JSON
- Use the browser to confirm reports auto-refresh and auto-select after evaluation

## 🛡️ Zod Validation Architecture

The dashboard uses **Zod v4 (`^4.4.3`)** for runtime request validation and shared type guarantees across the frontend-backend boundary.

### Server-Side Middleware (`src/backend/middleware/validation.ts`)

A `validate(schema)` middleware factory uses `safeParse` to check request bodies before they reach route handlers. On failure it returns a structured 400 response; on pass it calls `next()` with typed data.

```typescript
// Pattern: validate(schema) returns Express middleware
router.post("/api/commands/start", validate(startCommandSchema), handler);
```

**Failure response shape:**
```json
{ "error": "Validation failed", "details": "<Zod error messages>" }
```

### Validation Schemas

| Schema | File | Validates | Notes |
|--------|------|-----------|-------|
| `startCommandSchema` | `src/backend/middleware/validation.ts` | `commandId` (z.enum of 26 known ucore subcommands) + `args` string array | Enum exhaustively lists every `./ucore` subcommand |
| `stopJobSchema` | `src/backend/middleware/validation.ts` | `jobId` format, `signal` (optional, defaults to SIGTERM) | Allows graceful/custom signal termination |
| `createWorkflowSchema` | `src/backend/middleware/validation.ts` | workflow step chain and artifact paths | Multi-step pipeline orchestration |

### Wired Endpoints

- **POST /api/commands/start** — `validate(startCommandSchema)` → routes to command execution service
- **POST /api/commands/stop** — `validate(stopJobSchema)` → routes to job lifecycle service

The command validation router at `src/backend/routes/commands.ts` handles 20+ endpoints, all relying on these typed schemas.

### Frontend Integration

- **Typed request pipeline**: Frontend-validated data flows through the typed request pipeline to the server, eliminating ad-hoc shape checks in route handlers.
- **Eval report schemas** (`src/schemas/eval-reports.ts`): Shared Zod schemas between `EvalReportsPanel` and `EvalWorkflowPanel` prevent schema drift. Both panels derive their expected API shapes from the same source of truth.
- **ZodError detection** (`DatasetPipelinePanel`): Catches Zod validation errors at the API boundary and surfaces a "Data format mismatch from server" message when the backend returns an unexpected shape — no silent failures or cryptic type errors.
- **Error type convention**: Catch clauses use `unknown` instead of `Error` for safer type narrowing (`instanceof ZodError` checks work correctly without unsafe casts).
