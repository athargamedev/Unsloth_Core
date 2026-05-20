# Unified Registry & Logs Plan — Unsloth_Core

> **Goal**: A single, reliable source of truth for all pipeline registries and logs — covering dataset generation, DeepEval, and the frontend — with zero data loss, clear ownership, and a clean interface for the dashboard.

---

## 1. Diagnosis: Current State

### 1.1 What Exists Today

| Subsystem | Where state lives | Format | Problems |
|---|---|---|---|
| **Dataset generation** | `subjects/datasets/{npc}/{tech}/train.jsonl` + `train_manifest.json` | JSONL + JSON | Manifest schema varies; no run-level registry |
| **Sanitizer** | `train_manifest.json` (same dir, overwritten) | JSON | No history; overwrite-on-rerun |
| **DeepEval gate** | `quality_summary.json`, `quality_failures.json`, `quality_report.json` | JSON | Each rerun clobbers previous; no link to run ID |
| **DeepEval raw output** | `.deepeval/.latest_test_run.json` | JSON | Ephemeral; not versioned; not linked to NPC or run |
| **Training** | `outputs/{npc}/runs/{run_id}/config_snapshot.yaml`, `training_metrics.json` | YAML + JSON | Isolated per-run dir; no cross-run index |
| **Pipeline hooks** | `workflow_hooks.jsonl` (co-located with output dir) | JSONL | Multiple files; no single index; hook path is inconsistent across stages |
| **Feedback loop** | `eval/results/pipeline_state.json` | JSON | Single flat file for all NPCs; no run-level linkage |
| **Evaluation results** | `eval/reports/{npc}/`, `eval/results/feedback/` | MD + HTML + JSON | Report path generated daily; no run registry |
| **Frontend job registry** | `.runtime/registry.json` (in-memory + persisted) | JSON | Separate from Python pipeline; only tracks frontend-dispatched jobs |
| **Frontend job logs** | `.runtime/logs/{job_id}.log` | Text | Separate from `logs/` directory; no link to hook JSONL |
| **Server logs** | `.runtime/server.log` | Text | Rotated at 512 KB; no structured format |
| **Manual logs** | `logs/*.log` (e.g. `history_guide_ollama_generate_20260519.log`) | Text | Manually named; no indexing; ad-hoc |
| **Telemetry IPC** | `TelemetryReporter` writes a JSON file at an `ipc_path` | JSON | Path varies; not indexed; dashboard polls it separately |
| **W&B** | `wandb/` directory + Weights & Biases cloud | Mixed | Only training; not other stages |

### 1.2 Root Problems

1. **No canonical run ID** is shared across all 7 pipeline stages. Each stage invents its own ID (or none). The frontend `job_id` and the Python `run_id` are completely disjoint.
2. **Three separate log sinks** exist with no relation: `logs/` (manual text), `.runtime/logs/` (frontend jobs), `workflow_hooks.jsonl` (Python hooks). None cross-reference the others.
3. **Quality artifacts are overwritten** on every rerun. There is no archive. `quality_summary.json` from the 3rd gate run does not distinguish itself from the 1st.
4. **The frontend registry** (`registry.json`) only knows about jobs it launched. It has no visibility into pipeline runs triggered from the CLI or other tools.
5. **`pipeline_state.json`** is a flat dict keyed by `npc_key` and is updated by the feedback loop only. It does not represent the complete pipeline lifecycle.
6. **`log_state()` in `log_setup.py`** emits JSON to `stdout` but nothing consumes it systematically — the server captures job stdout as raw text.
7. **DeepEval's `.latest_test_run.json`** is a single mutable file. Two parallel `dataset-eval` runs on different NPCs would race and corrupt it.

---

## 2. Design: Unified Source of Truth

### 2.1 Core Concept — The Pipeline Run Record

Every pipeline invocation, regardless of stage or entrypoint (CLI, frontend, feedback loop), writes to a **single append-only run index** and a **per-run directory**.

```
.pipeline/
├── runs.jsonl                     ← append-only run index (THE source of truth)
├── runs/
│   └── {run_id}/
│       ├── meta.json              ← immutable run metadata (created once)
│       ├── workflow_hooks.jsonl   ← step lifecycle events (existing system)
│       ├── log_state.jsonl        ← structured log_state() events
│       └── artifacts/
│           ├── quality_summary.json    (symlink or copy from dataset dir)
│           ├── quality_failures.json
│           ├── training_metrics.json
│           └── eval_report.html
```

The **run ID** has this canonical format (already partially in `paths.py`):
```
{YYYYMMDD}_{npc_key}_{stage}_{preset_or_technique}_{seq:03d}
```

Example: `20260520_history_guide_train_fast-3b_001`

---

### 2.2 The Run Index — `runs.jsonl`

Each line is a **run record** appended atomically on start and updated on completion:

```jsonc
// START event (written immediately when any pipeline stage begins)
{
  "ts": "2026-05-20T23:00:00Z",
  "event": "start",
  "run_id": "20260520_history_guide_train_fast-3b_001",
  "npc_key": "history_guide",
  "stage": "train",           // generate | sanitize | dataset_eval | train | export | evaluate | feedback
  "technique": "template",
  "spec_path": "subjects/NPC_specs/history_guide.json",
  "preset": "fast-3b",
  "entrypoint": "cli",        // cli | frontend | feedback_loop | auto_retrain
  "frontend_job_id": null,    // set if launched by frontend
  "pid": 12345,
  "run_dir": ".pipeline/runs/20260520_history_guide_train_fast-3b_001"
}

// COMPLETE event (written on clean exit, updates the same run_id)
{
  "ts": "2026-05-20T23:05:30Z",
  "event": "complete",
  "run_id": "20260520_history_guide_train_fast-3b_001",
  "npc_key": "history_guide",
  "stage": "train",
  "status": "ok",
  "duration_s": 330,
  "artifacts": {
    "adapter_dir": "outputs/history_guide/runs/20260520_history_guide_train_fast-3b_001",
    "gguf": "exports/history_guide/history_guide-lora-f16.gguf"
  },
  "metrics": { "train_loss": 0.042, "num_examples": 118 }
}

// ERROR event (written on failure)
{
  "ts": "2026-05-20T23:03:10Z",
  "event": "error",
  "run_id": "...",
  "stage": "train",
  "error": "OutOfMemoryError",
  "message": "CUDA out of memory..."
}
```

#### Why JSONL and not a database?

- Zero dependencies — pure Python `open()` + `json.dumps()`
- Append-only → crash-safe; never corrupts existing records
- `WorkflowHookReader` already proves the pattern works at scale
- SQLite is an option for Phase 2 (indexing/querying), but JSONL is the write-first source of truth

---

### 2.3 New Module — `scripts/ops/run_registry.py`

This is the **only new Python file** required. All existing scripts call it.

```python
class RunRegistry:
    """Append-only run index. Thread-safe. Never raises (best-effort)."""

    INDEX_PATH = PROJECT_ROOT / ".pipeline" / "runs.jsonl"

    def __init__(self, index_path=None):
        self.index_path = Path(index_path or self.INDEX_PATH)

    def start_run(
        self, *, run_id, npc_key, stage, technique=None,
        spec_path=None, preset=None, entrypoint="cli",
        frontend_job_id=None, **extra
    ) -> Path:
        """Append a start record. Returns the run_dir path."""
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "run_id": run_id, "npc_key": npc_key, "stage": stage,
            "technique": technique, "spec_path": str(spec_path) if spec_path else None,
            "preset": preset, "entrypoint": entrypoint,
            "frontend_job_id": frontend_job_id,
            "pid": os.getpid(), "run_dir": str(run_dir), **extra
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        self._append("start", run_id=run_id, npc_key=npc_key, stage=stage, **meta)
        return run_dir

    def complete_run(self, run_id, *, artifacts=None, metrics=None, **extra):
        self._append("complete", run_id=run_id, status="ok",
                     artifacts=artifacts or {}, metrics=metrics or {}, **extra)

    def error_run(self, run_id, *, error, message="", **extra):
        self._append("error", run_id=run_id, status="error",
                     error=error, message=message, **extra)

    def _append(self, event, **fields):
        """Best-effort atomic append to runs.jsonl."""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            record = {"ts": isoNow(), "event": event, **fields}
            with _registry_lock:
                with self.index_path.open("a", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, default=str)
                    f.write("\n")
        except Exception:
            pass  # Registry must never break the pipeline

    def _run_dir(self, run_id) -> Path:
        return PROJECT_ROOT / ".pipeline" / "runs" / run_id

    def query(self, *, npc_key=None, stage=None, limit=50) -> list[dict]:
        """Read and filter the run index. For dashboard use."""
        ...

    def latest_run(self, npc_key, stage=None) -> dict | None:
        """Return the most recent complete run record for an NPC+stage."""
        ...

    def npc_summary(self, npc_key) -> dict:
        """Return a summary of all stages run for an NPC (for dashboard)."""
        ...
```

---

### 2.4 Unified Log Strategy

Three tiers, each with a clear purpose:

| Tier | Sink | Format | Consumer | When |
|---|---|---|---|---|
| **Human** | `stderr` via `log_setup._log` | `HH:MM:SS [LEVEL] msg` | Developer terminal | Always |
| **Structured events** | `.pipeline/runs/{run_id}/log_state.jsonl` | JSONL `{ts, event, ...}` | Dashboard, debugging | Every `log_state()` call |
| **Step lifecycle** | `.pipeline/runs/{run_id}/workflow_hooks.jsonl` | JSONL `{ts, step, status, ...}` | Dashboard, `WorkflowHookReader` | Every `with hook_recorder.step()` |

**Change to `log_state()`**: Instead of writing only to `stdout`, it also appends to the run-dir `log_state.jsonl` when a `run_id` is active:

```python
# _config/log_setup.py — updated log_state
_active_run_id: str | None = None
_active_run_dir: Path | None = None

def set_active_run(run_id: str, run_dir: Path):
    global _active_run_id, _active_run_dir
    _active_run_id = run_id
    _active_run_dir = run_dir

def log_state(event: str, **kwargs) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **kwargs}
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()
    # Also persist to run-dir if active
    if _active_run_dir:
        try:
            p = _active_run_dir / "log_state.jsonl"
            with p.open("a") as f:
                json.dump(payload, f, default=str)
                f.write("\n")
        except Exception:
            pass
```

---

### 2.5 Quality Artifact Versioning

Currently `quality_summary.json` is clobbered on every rerun. The fix is **non-destructive archive**:

```
subjects/datasets/{npc}/{tech}/
├── train_clean.jsonl
├── quality_summary.json           ← always the latest (symlink or copy)
├── quality_failures.json          ← always the latest
├── quality_report.json            ← always the latest
└── history/
    ├── quality_summary_{run_id}.json
    ├── quality_failures_{run_id}.json
    └── quality_report_{run_id}.json
```

`dataset_eval.py` writes the versioned file first, then updates the "latest" pointer atomically (rename/copy). This is a **2-line change** to `write_json()`.

---

### 2.6 Frontend ↔ Python Registry Bridge

The frontend `registry.json` tracks **frontend-dispatched jobs**. The Python `.pipeline/runs.jsonl` tracks **all pipeline runs**. They need to be linked.

#### Bridge mechanism — `run_id` in job metadata

When the frontend dispatches a command (`/api/commands/start`), the server:
1. Generates a deterministic `frontend_job_id` (already done: `job_${Date.now()}_${random}`)
2. Passes `--run-registry-job-id {frontend_job_id}` as an env var or CLI arg to the ucore command
3. Python scripts pick up `UCORE_FRONTEND_JOB_ID` and pass it to `RunRegistry.start_run(frontend_job_id=...)`

When the frontend polls `/api/jobs/state`, it can also call a new endpoint `/api/pipeline/runs` which reads `.pipeline/runs.jsonl` and returns runs not yet known to the frontend registry.

#### New server endpoint — `GET /api/pipeline/runs`

```typescript
app.get("/api/pipeline/runs", async (req, res) => {
  const limit = Number(req.query.limit) || 50;
  const npcKey = req.query.npc_key as string | undefined;
  const runsPath = path.join(repoRoot, ".pipeline", "runs.jsonl");
  const lines = readTailLines(runsPath, limit * 3);
  const records = lines
    .map(l => { try { return JSON.parse(l); } catch { return null; } })
    .filter(Boolean)
    .filter(r => !npcKey || r.npc_key === npcKey);
  res.json({ runs: records });
});
```

---

## 3. Implementation Plan

### Phase 1 — Core Infrastructure (No Breaking Changes)

**P1.1 — Create `scripts/ops/run_registry.py`**
- `RunRegistry` class with `start_run`, `complete_run`, `error_run`, `query`, `latest_run`, `npc_summary`
- Writes to `.pipeline/runs.jsonl` (append-only, file-locking)
- Returns `run_dir` path on `start_run`
- Fully standalone; no changes to existing scripts yet

**P1.2 — Update `_config/log_setup.py`**
- Add `set_active_run(run_id, run_dir)` and `clear_active_run()`
- `log_state()` writes to `run_dir/log_state.jsonl` when active
- Backward compatible — existing callers unchanged

**P1.3 — Update `default_hook_path()` in `workflow_hooks.py`**
- Accept optional `run_dir` parameter
- If `run_dir` is given, write hooks to `run_dir/workflow_hooks.jsonl` instead of `output_dir/workflow_hooks.jsonl`
- This is the single change that moves all hook files into `.pipeline/runs/{run_id}/`

**P1.4 — Add `.pipeline/` to `.gitignore`**
- The index is runtime state, not version-controlled
- Exception: `runs.jsonl` could optionally be committed (it's append-only and small)

---

### Phase 2 — Wire Into Existing Scripts

Each script gets **3 additions** at the top of `main()`:
1. `RunRegistry().start_run(...)` → returns `run_dir`
2. `log_setup.set_active_run(run_id, run_dir)`
3. Pass `run_dir` to `default_hook_path()` for the `WorkflowHookRecorder`

And **1 addition** at exit:
4. `RunRegistry().complete_run(run_id, artifacts=..., metrics=...)`

The `with hook_recorder.step()` pattern already handles error cases via `error` status — `run_registry.error_run()` can be called in the `except` block of the outer `with step()`.

**Scripts to update (in order):**

| Script | Stage label | Key artifacts to register |
|---|---|---|
| `generate_dataset.py` | `generate` | `train.jsonl`, row count, technique |
| `sanitize_dataset.py` | `sanitize` | `train_clean.jsonl`, discarded count, quality score histogram |
| `dataset_eval.py` | `dataset_eval` | `quality_summary.json`, pass rate, judge model |
| `train.py` | `train` | adapter dir, GGUF path, training loss |
| `export/export.py` / `export_adapter.py` | `export` | GGUF path, quantization |
| `evaluate.py` | `evaluate` | win rate, report path, candidate vs baseline |
| `feedback_loop.py` | `feedback` | weak concepts, regeneration decision, retrain status |

**Quality artifact versioning (P1.4 change to `dataset_eval.py`):**
```python
# After writing summary_path, failures_path, report_path:
history_dir = output_dir / "history"
history_dir.mkdir(exist_ok=True)
for src, name in [(summary_path, "quality_summary"), (failures_path, "quality_failures"), (report_path, "quality_report")]:
    dst = history_dir / f"{name}_{run_id}.json"
    shutil.copy2(src, dst)
```

---

### Phase 3 — Frontend Integration

**P3.1 — New server endpoint `/api/pipeline/runs`**
- Reads `.pipeline/runs.jsonl`
- Supports `?npc_key=`, `?stage=`, `?limit=` query params
- Returns `{runs: [...], total_events: N}`

**P3.2 — Bridge `frontend_job_id` → `run_id`**
- Server injects `UCORE_FRONTEND_JOB_ID={job.id}` into env when spawning pipeline commands
- Python `RunRegistry.start_run()` reads `os.getenv("UCORE_FRONTEND_JOB_ID")`
- The runs index records both `run_id` and `frontend_job_id`

**P3.3 — New dashboard panel — "Pipeline History"**
- Polls `/api/pipeline/runs?npc_key={selected}`
- Shows a table: `run_id | stage | status | duration | artifacts`
- Clicking a row expands the hook timeline (reads `.pipeline/runs/{run_id}/workflow_hooks.jsonl` via a new `GET /api/pipeline/runs/:run_id/hooks` endpoint)
- Replaces the need to manually tail `logs/*.log`

**P3.4 — Update existing `/api/jobs/state`**
- For each running/completed job, add a `run_id` field if one exists (by matching `frontend_job_id` in the runs index)
- This links the job table row to pipeline run data

**P3.5 — Replace manual `logs/` with structured run logs**
- `logs/*.log` files are hand-named ad-hoc logs with no index
- Going forward: the server writes job stdout/stderr to `.pipeline/runs/{run_id}/stdout.log`
- The frontend reads this via `GET /api/pipeline/runs/:run_id/log`
- The `logs/` directory is deprecated (kept for backward compatibility, not written to by any script)

---

### Phase 4 — NPC State Consolidation

**P4.1 — Replace `eval/results/pipeline_state.json`**

The current `pipeline_state.json` is a flat dict updated only by the feedback loop. Replace it with a **derived view** computed from `runs.jsonl`:

```python
# scripts/ops/run_registry.py
def npc_summary(self, npc_key: str) -> dict:
    """Compute current NPC state from the run index."""
    runs = self.query(npc_key=npc_key)
    complete_by_stage = {}
    for r in reversed(runs):
        stage = r.get("stage")
        if r.get("event") == "complete" and stage not in complete_by_stage:
            complete_by_stage[stage] = r
    return {
        "npc_key": npc_key,
        "last_generate": complete_by_stage.get("generate"),
        "last_sanitize": complete_by_stage.get("sanitize"),
        "last_dataset_eval": complete_by_stage.get("dataset_eval"),
        "last_train": complete_by_stage.get("train"),
        "last_export": complete_by_stage.get("export"),
        "last_evaluate": complete_by_stage.get("evaluate"),
        "last_feedback": complete_by_stage.get("feedback"),
        "pipeline_health": self._pipeline_health(complete_by_stage),
    }
```

**P4.2 — New server endpoint `GET /api/npc/:npc_key/status`**

Returns the computed NPC summary above. The frontend's NPC selector panel can display a health badge (all stages green / some pending / last run failed).

---

## 4. File & Directory Map (After Implementation)

```
Unsloth_Core/
├── .pipeline/                           ← NEW: runtime pipeline state
│   ├── runs.jsonl                       ← THE source of truth (append-only)
│   └── runs/
│       └── {run_id}/
│           ├── meta.json                ← immutable run metadata
│           ├── workflow_hooks.jsonl     ← step lifecycle (moved from output dirs)
│           ├── log_state.jsonl          ← structured log_state() events
│           ├── stdout.log               ← raw stdout from pipeline script
│           └── artifacts/
│               ├── quality_summary.json (symlink)
│               └── training_metrics.json (symlink)
│
├── _config/
│   ├── log_setup.py                     ← UPDATED: set_active_run(), dual-sink log_state()
│   └── paths.py                         ← UPDATED: pipeline_run_dir(), pipeline_index_path()
│
├── scripts/
│   └── ops/
│       ├── workflow_hooks.py            ← UPDATED: accept run_dir in default_hook_path()
│       └── run_registry.py             ← NEW: RunRegistry class
│
├── subjects/datasets/{npc}/{tech}/
│   ├── train.jsonl
│   ├── train_clean.jsonl
│   ├── quality_summary.json            ← latest (unchanged location)
│   ├── quality_failures.json           ← latest (unchanged location)
│   ├── quality_report.json             ← latest (unchanged location)
│   └── history/                        ← NEW: versioned archive
│       ├── quality_summary_{run_id}.json
│       └── quality_failures_{run_id}.json
│
└── frontend_control/unity-npc-llm-training-dashboard/
    └── server.ts                        ← UPDATED: /api/pipeline/runs, /api/npc/:key/status
```

---

## 5. API Contract Summary

| Endpoint | Method | Returns |
|---|---|---|
| `/api/pipeline/runs` | GET | `{runs: RunRecord[], total_events: N}` |
| `/api/pipeline/runs/:run_id` | GET | Full run record + merged hook events |
| `/api/pipeline/runs/:run_id/hooks` | GET | `{events: HookEvent[]}` |
| `/api/pipeline/runs/:run_id/log` | GET | `{lines: string[]}` (stdout.log) |
| `/api/npc/:npc_key/status` | GET | `NPCSummary` with per-stage latest run |
| `/api/jobs/state` | GET | *unchanged* + `run_id` field added to each job |

---

## 6. Migration Path (Zero-Downtime)

The plan is **additive only** in Phase 1-2. Existing scripts keep working; the registry is best-effort (never raises). Migration order:

1. ✅ Create `run_registry.py` (standalone, no imports changed)
2. ✅ Update `log_setup.py` (backward compatible)
3. ✅ Update `workflow_hooks.py` `default_hook_path` signature (backward compatible — `run_dir` defaults to `None`)
4. ✅ Wire `generate_dataset.py` first (most runs, easiest to test)
5. ✅ Wire remaining scripts in dependency order
6. ✅ Add quality history archiving to `dataset_eval.py`
7. ✅ Add frontend endpoints (additive — no existing endpoints removed)
8. ✅ Add Pipeline History panel to dashboard
9. ⚡ Deprecate `eval/results/pipeline_state.json` (kept for 1 release, then removed)
10. ⚡ Deprecate manual `logs/*.log` naming convention

---

## 7. Key Invariants (Rules for All Future Work)

> [!IMPORTANT]
> These rules must be enforced in code review and in AGENTS.md.

1. **One run_id per pipeline stage invocation.** Generated by `RunRegistry.start_run()` using the canonical `paths.generate_run_id()` format. Never invented ad-hoc inside a script.
2. **`RunRegistry` is best-effort.** Any exception inside registry calls is silently swallowed. It must never crash a pipeline stage.
3. **Quality artifacts are archived, never deleted.** `history/quality_{artifact}_{run_id}.json` always exists alongside the latest symlink.
4. **`workflow_hooks.jsonl` lives in the run_dir.** Not in the output dir, not in the dataset dir. The `default_hook_path(run_dir)` helper enforces this.
5. **`log_state()` is the only structured event emitter.** Do not invent new JSON-to-stdout patterns. `log_state()` routes to both stdout and `run_dir/log_state.jsonl`.
6. **Frontend job IDs and Python run IDs are linked, not merged.** They coexist via `frontend_job_id` field in the run record. Never replace one with the other.
7. **`.pipeline/runs.jsonl` is the source of truth.** `pipeline_state.json` and any other derived state files are computed from it, not maintained alongside it.
