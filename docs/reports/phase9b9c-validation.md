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

## Green-path marker validation (progressed into training)
Follow-up probe updated the pipeline API payload to pass through optional settings (`preset`, `options.technique`, `options.notebooklmInput`, `options.track`) so the dashboard can launch deterministic variants of pipeline runs.

Probe payload:
- commandId: `pipeline`
- spec: `subjects/chemistry_instructor.json`
- preset: `fast-3b`
- options.technique: `template`

Observed runtime state:
- status: `running`
- progress: `35`
- stages: `["completed","running","pending","pending"]`

Interpretation:
- Marker parser correctly advanced from dataset -> training using explicit `[STAGE]` markers.
- No false transitions to evaluation/export occurred while only training logs were present.

Operational note discovered:
- `/api/commands/stop` acknowledged request but did not terminate the active training subprocess chain in this run; manual PID termination was required.

## Stop reliability fix — process group kill (implemented)
Root cause: `spawn()` with default settings creates the child in the parent's process group. `process.kill("SIGTERM")` only signals the immediate child PID (e.g., `ucore`), not its subprocess tree (train.py, etc.).

Fix applied:
- Changed `spawn()` to use `{ detached: true }` — makes the child the leader of a new process group (PID == PGID).
- Changed stop handler from `process.kill("SIGTERM")` to `process.kill(-proc.pid, "SIGTERM")` — negative PID kills the entire process group.
- Same fix applied to escalation timer (SIGKILL path).
- Fixed pre-existing variable shadowing bug: stop handler variable `process` renamed to `proc` to avoid shadowing the Node.js global `process` object.
- Added `"stopped"` to `Stage.status` union type in both server.ts and App.tsx.
- Separated "stopped" stage mapping from "failed" in `updateStagesFromTruth()` — stopped jobs now show active stage as `"stopped"` instead of `"failed"`.
- Added `"stopped"` visual styling in WorkflowVisualizer and detail view.

Verification test:
- Started pipeline command, waited until training phase (stage[1] == "running").
- Issued `POST /api/commands/stop` → response `{ status: "stop_requested" }`.
- Observed immediate state transition to `stopped` with stages `["completed","stopped","pending","pending"]`.
- Verified zero orphaned pipeline processes after stop.

