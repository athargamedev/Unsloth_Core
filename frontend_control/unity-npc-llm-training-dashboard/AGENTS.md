# frontend_control/unity-npc-llm-training-dashboard/ AGENTS

## Purpose
This folder contains the dashboard backend and frontend code that orchestrate jobs, evaluation, reports, and live state.

## Rules
- Treat the backend command builder in `server.ts` as the source of truth for CLI flag wiring.
- Keep frontend forms, payloads, and server command schemas in sync.
- Eval reporting must preserve HTML report generation, tracking, judge mode, judge model, base model, LoRA weight, question count, and feedback JSON support.
- Prefer backend-owned state over frontend inference for jobs, reports, and progress.
- When changing paths or defaults, verify both the API shape and the rendered UI.
- Keep compatibility with existing `./ucore` commands and root scripts wrappers.

## Quick checks
- `npm run build`
- Verify `/api/jobs/state` and `/api/eval-reports` return the expected JSON
- Use the browser to confirm reports auto-refresh and auto-select after evaluation
