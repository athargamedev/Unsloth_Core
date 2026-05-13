# Phase 9 Perfection Plan — Export Determinism + Full Frontend Control Integration

Status: Drafted for immediate execution
Owner: Unsloth_Core
Goal: Deterministic end-to-end pipeline + truthful frontend control-plane where every shown value is real and actionable.

## 0) Success Criteria (Release Gate)

All must be true:
1. No pipeline stage can run indefinitely without timeout/failure.
2. `frontend_control` commands exactly match current `ucore` CLI contracts.
3. Every dashboard metric/panel maps to a real backend source (or clearly labeled simulated).
4. Golden workflow produces pass/fail JSON artifact with stage evidence.
5. Supabase health/probe status is visible in API + UI.

---

## 1) Phase 9A — Export/Quantization Determinism

### 1.1 Add export watchdog + heartbeat
Files:
- `scripts/export.py`
- optionally shared helpers in `_config/` or `scripts/`

Tasks:
- Add substep timers: merge_timeout, convert_timeout, quant_timeout, stall_timeout.
- Emit heartbeat logs every N seconds per substep.
- Detect stall (no log/progress for `stall_timeout`) and hard-fail with structured reason.

Verify:
- Run export on known adapter and confirm periodic heartbeat lines.
- Simulate stall by killing child substep; confirm fail reason appears within timeout.

### 1.2 Add structured export status artifact
Files:
- `scripts/export.py`
- output file: `exports/{npc_key}/export_status.json`

Schema:
- `state`: pending|running|stalled|failed|completed
- `substep`: merge|convert|quantize|finalize
- timestamps, pid, retries, error_summary, last_heartbeat

Verify:
- Status transitions update in real time and final state is terminal.

### 1.3 Ensure recursive child process control
Files:
- `scripts/export.py`
- `frontend_control/.../server.ts` (stop escalation already exists; ensure coverage)

Tasks:
- Track child process tree for quantization/conversion.
- On stop: SIGTERM -> grace -> SIGKILL with final terminal_reason.
- Prevent orphan `llama-quantize`.

Verify:
- Start export, stop job, confirm no lingering quantize process with `pgrep -fa llama-quantize`.

### 1.4 Add resumable export command
Files:
- `ucore`
- `scripts/export_resume.py` (new)

Tasks:
- `./ucore export-resume --npc-key <key> [--model ...] [--quantization ...]`
- Reuse valid intermediates based on checksum/state file.

Verify:
- Interrupt export mid-quantize, run resume, confirm continuation and completion.

---

## 2) Phase 9B — Truthful Pipeline State Instrumentation

### 2.1 Structured job event stream
Files:
- `frontend_control/unity-npc-llm-training-dashboard/server.ts`
- runtime path `.runtime/events/{job_id}.jsonl`

Event types:
- `stage_started`, `stage_progress`, `stage_completed`, `stage_failed`, `job_completed`, `job_failed`, `job_stopped`

Verify:
- Trigger job, confirm event stream monotonic and consistent with final job state.

### 2.2 Replace heuristic progress inference
Files:
- `server.ts`
- `src/App.tsx`

Tasks:
- Remove progress guessing from regex/log-only increments.
- Drive UI progress/stage state from backend stage events.

Verify:
- Stage visuals align with emitted events; no contradictory statuses.

### 2.3 Persist full job evidence bundle
Files:
- `.runtime/registry.json` schema extension

Fields:
- command, args, cwd, pid_tree, startedAt/finishedAt, exitCode, terminalReason
- artifacts produced, warnings, blockers, status_summary

Verify:
- Completed and failed jobs expose full forensic context in API.

---

## 3) Phase 9C — Frontend Information Integrity Completion

### 3.1 UI-to-data-source contract audit
Files:
- `src/App.tsx`
- `server.ts`
- new doc table in `frontend_control/DOCUMENTATION.md`

Tasks:
- Build matrix: widget label -> endpoint -> field -> freshness interval.
- Identify mock/hardcoded values and classify remove/replace/label.

Verify:
- No unresolved widget remains in audit table.

### 3.2 Add missing API endpoints for detailed drilldowns
Files:
- `server.ts`

Endpoints:
- `GET /api/jobs/:id/stage-events`
- `GET /api/jobs/:id/artifacts`
- `GET /api/runs/:id/manifest`
- `GET /api/system/resources` (if available; otherwise explicitly unavailable status)

Verify:
- Endpoints return typed payloads and handle not-found cleanly.

### 3.3 Replace `window.prompt` command input flow
Files:
- `src/App.tsx`

Tasks:
- Add typed command forms with inline validation.
- Path fields validated before submit.
- Preset/spec dropdowns sourced from API.

Verify:
- All command runs possible from UI with no prompt popups.

### 3.4 Supabase observability in UI
Files:
- `src/App.tsx`
- `server.ts`

Tasks:
- Show `/api/health` check details.
- Surface latest supabase-check job outcome and error summary.

Verify:
- Missing envs displayed as explicit blockers; valid envs show ready state.

---

## 4) Phase 9D — Golden Workflow Test Harness

### 4.1 Create deterministic harness
Files:
- `scripts/golden_workflow_test.py` (new)

Flow:
1. generate
2. sanitize
3. train (smoke)
4. export
5. smoke `--check-integrity`
6. evaluate quick
7. supabase-check (`--skip-probe` then full if envs present)
8. dashboard API consistency checks

Output:
- `eval/results/golden_workflow_{timestamp}.json`

Verify:
- Single command run produces full matrix with terminal pass/fail per stage.

### 4.2 Add strict rubric
Fields per stage:
- `status`: pass|fail|skipped
- `duration_s`
- `artifact_paths`
- `error_summary`
- `blocking`

Verify:
- Failures are machine-diagnosable and human-readable.

---

## 5) Phase 9E — Release Hardening

### 5.1 Contract drift tests
Files:
- `tests/` add command-contract tests

Tasks:
- Validate command builders in `server.ts` emit only supported `ucore` flags.
- Validate required fields map to real CLI requirements.

### 5.2 Operational safeguards
Files:
- `server.ts`

Tasks:
- max concurrent jobs config
- duplicate job suppression window
- queue semantics for long jobs

### 5.3 Documentation parity
Files:
- `frontend_control/DOCUMENTATION.md`
- `docs/EVALUATION_WORKFLOW.md` (if endpoint behavior changes)

Tasks:
- Remove obsolete/fictional claims.
- Add exact API and command examples used by UI.

---

## 6) Task IDs and Sequence

Execution order (mandatory):
- P9A-1..4
- P9B-1..3
- P9C-1..4
- P9D-1..2
- P9E-1..3

Suggested IDs:
- P9A-1 watchdog-heartbeat
- P9A-2 export-status-artifact
- P9A-3 child-process-hardening
- P9A-4 export-resume
- P9B-1 job-event-stream
- P9B-2 truthful-progress
- P9B-3 job-evidence-bundle
- P9C-1 ui-data-contract-audit
- P9C-2 missing-endpoints
- P9C-3 typed-command-forms
- P9C-4 supabase-observability
- P9D-1 golden-harness
- P9D-2 scoring-rubric
- P9E-1 contract-drift-tests
- P9E-2 operational-safeguards
- P9E-3 doc-parity

---

## 7) Verification Commands (Core)

Backend + frontend compile:
- `python -m py_compile scripts/*.py`
- `cd frontend_control/unity-npc-llm-training-dashboard && npm run lint && npm run build`

Dashboard runtime checks:
- `PORT=3100 npm run dev`
- `curl -s http://localhost:3100/api/health`
- `curl -s http://localhost:3100/api/available-commands`

Golden workflow:
- `python scripts/golden_workflow_test.py --npc-key chemistry_instructor --technique template --preset smoke`

Export stall/resume drill:
- start export, interrupt, then:
- `./ucore export-resume --npc-key chemistry_instructor`

No orphan processes:
- `pgrep -fa "llama-quantize|convert_hf_to_gguf|ucore"`

---

## 8) Non-Negotiable Quality Bar

No “probably done.”
Done means:
- deterministic terminal states,
- truthful UI,
- reproducible golden pass artifact,
- zero command/API contract drift.
