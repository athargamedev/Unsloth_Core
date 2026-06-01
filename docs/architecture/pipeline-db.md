# Pipeline Database Integration (Python)

## Overview

`scripts/ops/pipeline_db.py` provides the `PipelineDB` class (1,837 lines, ~65 methods, 20 public API methods) that lets pipeline scripts write state to the Supabase/PostgreSQL pipeline tables. It supports two connection modes and auto-detects the best available option.

## Connection Modes

### Direct PostgreSQL (Preferred)
Uses `psycopg2` for full CRUD via parameterized SQL. Connection configured via:

| Env Variable | Purpose |
|-------------|---------|
| `SUPABASE_DB_URL` | Primary PostgreSQL connection string |
| `PIPELINE_DB_URL` | Optional override for DB connection string |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` | Individual connection params |

### REST API Fallback
Uses Supabase REST API via `urllib` (stdlib only, no extra dependencies). Connection configured via:

| Env Variable | Purpose |
|-------------|---------|
| `SUPABASE_URL` | Base URL for REST API (e.g. `http://localhost:16437`) |
| `SUPABASE_KEY` | Anon or service key |

### Local Default
When neither connection method is configured, the class falls back to:

```
host=127.0.0.1 port=15434 user=postgres password=postgres dbname=postgres
```

This matches the defaults of a `supabase start` local instance.

## Auto-Detection

`create_pipeline_db()` (in `scripts/ops/workflow_hooks.py`) handles auto-detection:

```python
from scripts.ops.workflow_hooks import create_pipeline_db

db = create_pipeline_db()  # Tries env vars → localhost:15434
```

Priority order:
1. `PIPELINE_DB_URL` (explicit override)
2. `SUPABASE_DB_URL` (primary connection string)
3. `SUPABASE_URL` + `SUPABASE_KEY` (REST API fallback)
4. Localhost defaults

## Public API Methods

### Jobs
| Method | Description |
|--------|-------------|
| `create_job(npc_key, type, command_id, command_args, ...)` | Insert new pipeline job |
| `update_job_status(job_id, status, exit_code, error, ...)` | Update job state |
| `get_job(job_id)` | Fetch a single job |
| `list_jobs(npc_key, status, limit, offset)` | List jobs with filters |

### Runs
| Method | Description |
|--------|-------------|
| `create_run(npc_key, run_id, run_dir, preset, technique, ...)` | Insert training run |
| `update_run_metrics(run_id, metrics, loss, ...)` | Update run metrics |
| `get_run(run_id)` | Fetch a single run |
| `list_runs(npc_key, limit, offset)` | List runs with filters |

### Artifacts
| Method | Description |
|--------|-------------|
| `create_artifact(npc_key, artifact_type, file_path, ...)` | Record a generated file |
| `list_artifacts(npc_key, artifact_type, limit)` | List artifacts with filters |

### Quality Gates
| Method | Description |
|--------|-------------|
| `create_quality_gate(npc_key, technique, pass_rate, total, passed, failed, ...)` | Record DeepEval gate result |

### Eval Sessions
| Method | Description |
|--------|-------------|
| `create_eval_session(npc_key, total, baseline_wins, candidate_wins, win_rate, per_concept, ...)` | Record evaluation result |

### Config Snapshots
| Method | Description |
|--------|-------------|
| `save_config_snapshot(npc_key, preset, technique, full_config, file_path)` | Freeze training config |

### Auth
| Method | Description |
|--------|-------------|
| `validate_api_key(key)` | Validate an API key against bcrypt hash (used by setup_admin_key.py) |
| `log_audit_event(...)` | Insert audit log entry |

### Sync
| Method | Description |
|--------|-------------|
| `sync_from_filesystem(path)` | Bulk import filesystem artifacts into pipeline tables |

Each method has two implementations (e.g. `_direct_create_job` and `_rest_create_job`) auto-selected by the connection mode.

## Integration with WorkflowHookRecorder

The `WorkflowHookRecorder` class (`scripts/ops/workflow_hooks.py`) integrates with PipelineDB so that every `step()` context manager in pipeline scripts automatically writes to the database:

```python
from scripts.ops.workflow_hooks import WorkflowHookRecorder, create_pipeline_db

db = create_pipeline_db()
recorder = WorkflowHookRecorder(
    hook_path="outputs/history_guide/runs/run_20260520/workflow_hooks.jsonl",
    tool="ucore",
    npc_key="history_guide",
    db=db,  # Optional DB client
)

with recorder.step("generate_dataset", spec_path=spec, run_id=run_id) as ctx:
    # Pipeline work...
    # Auto-writes: pipeline_jobs (on start), pipeline_runs (on start),
    # pipeline_artifacts (on complete/error), pipeline_config_snapshots (on training start)
    pass
```

What gets written:
- **pipeline_jobs**: Created on `step` entry (`status="start"`), updated on exit (`"complete"` or `"error"`)
- **pipeline_runs**: Created alongside jobs, tracks run metadata
- **pipeline_artifacts**: Created on step completion with file path, checksum, and size
- **pipeline_config_snapshots**: Saved when training steps begin

## Best-Effort Writes

All database writes are wrapped in `try/except` blocks. Pipeline scripts **never fail** due to a database write error. If Supabase is not running, the pipeline continues without tracking:

```python
try:
    db = create_pipeline_db()
    if db and db.ensure_connected():
        db.create_job(...)
except Exception:
    logger.warning("DB write failed — continuing pipeline")
```

## Column Allowlist

Dynamic SQL column names are validated against the `SANITIZE_ALLOWLIST` set to prevent SQL injection:

```python
SANITIZE_ALLOWLIST: set[str] = {
    "status", "progress", "error", "wandb_url", "logs", "name",
    "role", "is_active", "key_prefix", "version", "config",
    "spec_path", "run_id", "technique", "preset", "base_model",
    "npc_key", "category", "score", "pass_rate", "total", "passed",
    "failed", "failure_reason", "recommendation", "stage", "model",
    "model_id", "duration", "method", "path", "status_code",
    "ip_address", "request_body", ...
}
```

Any column name not in this set is rejected before hitting the database.

## Migration Management

Database schema changes are managed via Supabase migrations in `supabase/migrations/`:

```bash
# Apply all migrations locally
supabase db reset
```

Migration files are numbered by date and purpose:
- `20260512000001_create_npc_dialogue_schema.sql` — Runtime tables
- `20260521000001_create_pipeline_tables.sql` — Pipeline tables + functions
- `20260521000002_enable_realtime_pipeline.sql` — Realtime publication
- `20260521000003_add_spec_path_to_pipeline_runs.sql` — Column additions
- `20260521000004_enable_pipeline_extensions.sql` — pg_trgm, fuzzystrmatch
- `20260521000005_add_status_to_pipeline_runs.sql` — Status column + index

Always add new columns or schema changes via migrations, never via direct psql.
