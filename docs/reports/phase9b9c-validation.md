# Phase 9B/9C Validation Report

Timestamp: 2026-05-13T02:53:00Z

## Scope
Validated frontend control-plane truthfulness updates:
- deterministic stage/status mapping by command type
- real terminal state propagation
- API contract stability for `/api/commands/start`
- TypeScript/build integrity

## Build/Lint Validation
- `npm run lint` (frontend dashboard): PASS
- `npm run build` (frontend dashboard): PASS

## Runtime API Validation
Server started on `PORT=3100` with built artifact.

Endpoint checks:
- `GET /api/system/status` -> 200
- `GET /api/jobs` -> 200
- `POST /api/commands/start` with unknown commandId -> 400

## Golden Workflow Probe
Triggered command via API:
- commandId: `pipeline`
- spec: `subjects/chemistry_instructor.json`
- job id: `job_1778640772824_plncv`

Observed timeline:
- t=0s
  - status: `failed`
  - progress: `90`
  - stages: `["completed","completed","completed","failed"]`
  - last_log: `Error: Command failed with return code 2`

Interpretation:
- Terminal failure state is propagated deterministically.
- Stage model remains deterministic and no longer uses naive +1 progress increments per log line.
- Current pipeline-stage inference for pipeline jobs is log-token based and can over-credit prior stages when logs include stage keywords before failure; this is deterministic but conservative truthfulness hardening can be improved by adding explicit stage markers in `ucore pipeline` output.

## Artifacts
- Backend changes: `frontend_control/unity-npc-llm-training-dashboard/server.ts`
- Frontend compile fixes: `frontend_control/unity-npc-llm-training-dashboard/src/App.tsx`

## Stage marker hardening (implemented)
Implemented explicit stage markers in `ucore pipeline` output:
- `[STAGE] dataset`
- `[STAGE] training`
- `[STAGE] evaluation`
- `[STAGE] export`
- `[STAGE] complete`

Updated dashboard server parser to infer pipeline stage from explicit markers only.

Validation rerun:
- Triggered `pipeline` via API with no NotebookLM input (expected early failure)
- Observed deterministic stage result at failure:
  - status: `failed`
  - progress: `10`
  - stages: `["failed","pending","pending","pending"]`
- Confirmed last logs include `[STAGE] dataset` marker and no false advancement to later stages.
