---
name: unsloth-core-dashboard
description: Use when changing, testing, or debugging the Unsloth_Core dashboard under src/dashboard/unity-npc-llm-training-dashboard, including backend command wiring, Zod schemas, job state, reports, and rendered UI.
---

# Unsloth_Core Dashboard

Read `src/dashboard/unity-npc-llm-training-dashboard/AGENTS.md` before edits. Use Build Web Apps frontend testing/debugging guidance when visual behavior or browser flows matter.

## Rules

- `server.ts` and backend routes own CLI command wiring.
- Keep frontend payloads, backend schemas, and route responses synchronized.
- Eval reporting must preserve HTML report generation, tracking, judge mode/model, base model, LoRA weight, question count, and feedback JSON.
- Prefer backend-owned job/report state over frontend inference.
- Use Zod schemas for API boundary validation and shared response contracts.

## Commands

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run build
npm run dev
```

When running a dev server, give the user the local URL and verify relevant UI paths if browser tooling is available.

## Verification Targets

- `GET /api/jobs/state`
- `GET /api/eval-reports`
- command start/stop routes using typed validation
- report auto-refresh and selection after eval
- no text overlap or broken controls in changed panels

## Report Format

Use:

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```

