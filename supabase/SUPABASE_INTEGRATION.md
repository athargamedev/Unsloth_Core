# Supabase Integration in Unsloth_Core

> How the NPC training pipeline, dashboard backend, and Edge Functions connect to Supabase for persistent state management.

## Table of Contents

- [1. Current Integration](#1-current-integration)
  - [Database Schema](#database-schema)
  - [Extensions](#extensions)
  - [Migrations](#migrations)
  - [How Pipeline Scripts Connect](#how-pipeline-scripts-connect)
  - [What Gets Written Per Stage](#what-gets-written-per-stage)
  - [Auth System](#auth-system)
  - [Docker Services](#docker-services)
  - [Edge Functions](#edge-functions)
  - [Realtime](#realtime)
- [2. Future Ideas](#2-future-ideas)
  - [Short-Term](#short-term)
  - [Medium-Term](#medium-term)
  - [Long-Term](#long-term)

---

## 1. Current Integration

The project uses a local Supabase instance (`supabase start`) as its primary database. All pipeline state — jobs, runs, artifacts, evaluations, configs, API keys, and audit logs — lives in PostgreSQL tables managed by Supabase. The integration is **best-effort**: the pipeline scripts never block on database writes, and they degrade gracefully when the database is unavailable (writing only to local JSONL files instead).

### Database Schema

Eight pipeline tables are defined in `supabase/migrations/20260521000001_create_pipeline_tables.sql`, plus three NPC dialogue tables from earlier migrations.

#### pipeline_jobs — PostgreSQL-backed job queue

Every command execution creates a row here. This table is the foundation of the job queue — it supports `FOR UPDATE SKIP LOCKED` polling, PID tracking, exponential backoff retry, and survives server restarts.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `npc_key` | TEXT | Which NPC this job targets |
| `type` | TEXT | `Dataset`, `Training`, `Evaluation`, `Export`, `Validation`, `Feedback`, `System`, or `Pipeline` |
| `command_id` | TEXT | Unique command identifier |
| `command_args` | JSONB | CLI arguments for the command |
| `status` | TEXT | `pending`, `running`, `completed`, `failed`, `stopped`, `paused` |
| `progress` | INTEGER | 0–100 percent |
| `loss` | REAL | Training loss (populated on training jobs) |
| `exit_code` | INTEGER | Process exit code |
| `error` | TEXT | Error message on failure |
| `wandb_url` | TEXT | W&B run URL if tracking is enabled |
| `workflow_id` | TEXT | Workflow chain identifier |
| `chain_next` | JSONB | Next step in a multi-step workflow |
| `logs` | TEXT[] | Job log lines |
| `metadata` | JSONB | Retry count, next retry time, etc. |
| `spec_path` | TEXT | NPC spec file path |
| `created_at` / `updated_at` / `started_at` / `finished_at` | TIMESTAMPTZ | Timing columns |

**Indexes:** status, npc_key, created_at (DESC).

#### pipeline_runs — Training and evaluation run metadata

One row per training or evaluation execution, tracking configuration and results.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `job_id` | UUID FK → pipeline_jobs | Optional link to parent job |
| `npc_key` | TEXT | Target NPC |
| `run_id` | TEXT | Unique run identifier (unique per npc_key) |
| `run_dir` | TEXT | Output directory for the run |
| `status` | TEXT | `pending`, `ok`, `failed`, etc. |
| `preset` | TEXT | Training preset used |
| `model_id` | TEXT | Model identifier |
| `technique` | TEXT | Generation technique |
| `base_model` | TEXT | Base model ID |
| `spec_path` | TEXT | NPC spec file path |
| `config_snapshot` | JSONB | Frozen training config at time of run |
| `metrics` | JSONB | Loss, duration_s, num_examples, etc. |
| `lora_config` | JSONB | LoRA hyperparameters |
| `wandb_enabled` | BOOLEAN | W&B tracking flag |
| `wandb_url` | TEXT | W&B run URL |
| `has_adapter` | BOOLEAN | Whether a LoRA adapter was produced |
| `has_tensorboard` | BOOLEAN | Whether TensorBoard logs exist |
| `created_at` / `updated_at` / `finished_at` | TIMESTAMPTZ | Timing columns |

**Indexes:** npc_key, created_at (DESC), status.

#### pipeline_artifacts — Generated file tracking

Every file the pipeline produces — raw datasets, cleaned datasets, adapters, GGUFs, eval reports — gets a row here.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `npc_key` | TEXT | Target NPC |
| `run_id` | TEXT | Optional run identifier |
| `job_id` | UUID FK → pipeline_jobs | Optional link to parent job |
| `artifact_type` | TEXT | `dataset_raw`, `dataset_clean`, `adapter`, `gguf_adapter`, `gguf_full`, `eval_report`, `feedback_json`, `config_snapshot`, or `other` |
| `technique` | TEXT | Generation technique |
| `file_path` | TEXT | Path to the artifact on disk |
| `file_size_bytes` | BIGINT | File size |
| `file_hash` | TEXT | Content hash |
| `metadata` | JSONB | Extra metadata |
| `created_at` | TIMESTAMPTZ | Creation time |

**Indexes:** npc_key, artifact_type.

#### dataset_quality_gates — DeepEval quality gate results

One row per DeepEval evaluation run, storing pass/fail rates per category.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `npc_key` | TEXT | Target NPC |
| `technique` | TEXT | Generation technique |
| `job_id` | UUID FK → pipeline_jobs | Optional link to parent job |
| `dataset_path` | TEXT | Path to the evaluated dataset |
| `judge_model` | TEXT | Ollama model used as judge |
| `total_samples` | INTEGER | Total samples evaluated |
| `passed` / `failed` | INTEGER | Pass/fail counts |
| `pass_rate` | REAL | 0.0–1.0 pass rate |
| `metrics` | JSONB | Overall evaluation metrics |
| `categories` | JSONB | Per-category breakdown |
| `failures` | JSONB | Failure details array |
| `failures_path` | TEXT | Path to failures JSON file |
| `created_at` | TIMESTAMPTZ | Creation time |

**Indexes:** npc_key, created_at (DESC).

#### eval_sessions — Side-by-side model evaluation

Stores head-to-head comparisons between baseline and candidate models.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `npc_key` | TEXT | Target NPC |
| `baseline_artifact_id` | UUID FK → pipeline_artifacts | Baseline model artifact |
| `candidate_artifact_id` | UUID FK → pipeline_artifacts | Candidate model artifact |
| `total_examples` | INTEGER | Number of evaluation prompts |
| `baseline_wins` / `candidate_wins` / `ties` | INTEGER | Win/loss/tie counts |
| `win_rate` | REAL | Candidate win rate |
| `per_concept` | JSONB | Per-concept win/loss breakdown |
| `weak_concepts` | TEXT[] | Concepts where the candidate underperformed |
| `feedback_json_path` / `report_html_path` | TEXT | Paths to generated reports |
| `metadata` | JSONB | Extra metadata (judge model, paths, etc.) |
| `created_at` | TIMESTAMPTZ | Creation time |

**Indexes:** npc_key, created_at (DESC).

#### pipeline_config_snapshots — Frozen training configurations

Immutable record of training configs at the time each run was started. Essential for reproducibility.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `npc_key` | TEXT | Target NPC |
| `preset` | TEXT | Training preset |
| `technique` | TEXT | Generation technique |
| `full_config` | JSONB | Complete frozen configuration |
| `file_path` | TEXT | Optional path to config file |
| `hash` | TEXT | Content hash |
| `created_at` | TIMESTAMPTZ | Creation time |

**Indexes:** npc_key.

#### api_keys — bcrypt-hashed API key storage

Stores hashed API keys for the dashboard auth middleware. Keys are 64-char hex tokens; only the bcrypt hash is stored permanently. The first 8 characters (prefix) are stored separately for indexed lookups.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `key_hash` | TEXT | bcrypt hash of the full key |
| `key_prefix` | TEXT | First 8 hex characters (indexed lookup) |
| `name` | TEXT | Human-readable key name |
| `role` | TEXT | `admin`, `operator`, or `viewer` |
| `is_active` | BOOLEAN | Whether the key is currently active |
| `last_used_at` | TIMESTAMPTZ | Timestamp of last use |
| `created_at` | TIMESTAMPTZ | Creation time |
| `expires_at` | TIMESTAMPTZ | Optional expiration |

#### api_audit_log — Request audit trail

Every mutation request to the dashboard API is logged here. Sensitive fields (passwords, keys, tokens) are redacted before storage.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Auto-generated row ID |
| `api_key_id` | UUID FK → api_keys | Which key made the request |
| `user_role` | TEXT | Role at time of request |
| `method` | TEXT | HTTP method |
| `path` | TEXT | Request path |
| `status_code` | INTEGER | HTTP response status |
| `request_body` | TEXT | Redacted request body (first 2000 chars) |
| `ip_address` | TEXT | Client IP |
| `duration_ms` | INTEGER | Request processing time |
| `created_at` | TIMESTAMPTZ | Creation time |

**Indexes:** path, created_at (DESC).

#### NPC Dialogue Tables (earlier migrations)

Three additional migrations set up the runtime NPC dialogue schema:

- **`20260512000001`** — Core dialogue schema: `player_profiles`, `npc_profiles`, `dialogue_sessions`, `dialogue_turns`, `npc_memories`, `npc_knowledge`, and supporting indexes, RLS policies, and helper functions.
- **`20260512000002`** — Hybrid search: FTS vector on `npc_memories`, a `search_memories_hybrid()` function combining vector similarity and full-text search via weighted scoring.
- **`20260512000003`** — Memory consolidation: `touch_memory()` (importance boost on access), `apply_memory_decay()` (reduce importance of stale memories), `consolidate_memories()` (merge near-duplicate memories).

These tables are designed for the Unity runtime but are not yet populated by the pipeline — they are ready for when the player-facing system goes live.

### Extensions

The project enables 14 PostgreSQL extensions. The ones most relevant to pipeline operations are:

| Extension | Version | Purpose | Migrated In |
|-----------|---------|---------|-------------|
| `pgcrypto` | — | Cryptographic functions (UUID generation, hashing) | `20260512000001` |
| `vector` | 0.5.1 | Embedding storage and cosine similarity (semantic NPC memory) | `20260512000001` |
| `pg_trgm` | 1.6 | Trigram fuzzy text matching (NPC memory search, duplicate detection) | `20260521000004` |
| `fuzzystrmatch` | 1.2 | Levenshtein + Soundex (fuzzy name matching, input tolerance) | `20260521000004` |
| `hypopg` | — | Hypothetical indexes (query optimization experiments) | Supabase template |
| `index_advisor` | — | Index recommendation | Supabase template |
| `pgaudit` | — | Database-level audit logging | Supabase template |
| `plpgsql_check` | — | PL/pgSQL function validation | Supabase template |

The remaining extensions (`pg_cron` for job scheduling, `pgmq` for message queuing) are **commented out** in migration 4 — they are available for future use but require additional configuration (`shared_preload_libraries`).

### Migrations

Five pipeline-specific migrations plus three NPC dialogue migrations, applied in order:

| Migration | Purpose |
|-----------|---------|
| `20260512000001` | NPC dialogue schema — player_profiles, npc_profiles, dialogue_sessions, npc_memories, etc. |
| `20260512000002` | Hybrid search — FTS vector + search_memories_hybrid() function |
| `20260512000003` | Memory consolidation — touch_memory(), apply_memory_decay(), consolidate_memories() |
| `20260521000001` | Core pipeline tables + 3 helper PL/pgSQL functions + indexes + RLS policies |
| `20260521000002` | Realtime publication for 6 pipeline tables |
| `20260521000003` | Add spec_path + updated_at to pipeline_runs, spec_path to pipeline_jobs |
| `20260521000004` | Enable pg_trgm + fuzzystrmatch extensions |
| `20260521000005` | Add status column + index to pipeline_runs |

Migrations are run by `supabase db push` or `supabase migration up`. During local development, `supabase db reset` destroys and recreates the database from scratch, running all migrations in order.

#### PL/pgSQL Helper Functions

The first pipeline migration includes three stored procedures:

- **`upsert_pipeline_job(npc_key, type, command_id, command_args)`** — Creates a new job or updates an existing pending/running job for the same npc+command pair.
- **`complete_pipeline_job(job_id, status, exit_code, error)`** — Marks a job as completed/failed/stopped with timing and error info. Raises an exception if the job ID is not found.
- **`insert_pipeline_artifact(npc_key, artifact_type, file_path, ...)`** — Records a generated artifact with optional metadata.

#### Row-Level Security

All 8 pipeline tables have RLS enabled with **open policies** (`FOR ALL USING (true) WITH CHECK (true)`). These are temporary placeholders — the comment in the migration notes that they should be replaced with role-based policies once the auth system is fully integrated with Supabase Auth.

### How Pipeline Scripts Connect

The connection flows through two layers:

#### Layer 1: PipelineDB (`scripts/ops/pipeline_db.py`)

`PipelineDB` is a 1,838-line dual-mode database client with 60 methods (20 public, 40 internal private implementations). Every public method has a `_direct_` and `_rest_` variant, giving the class two operating modes:

**Direct PostgreSQL mode (preferred):**
- Uses `psycopg2` for full CRUD via SQL.
- Connection from `SUPABASE_DB_URL` or `PIPELINE_DB_URL` env vars.
- Falls back to `postgresql://postgres:postgres@127.0.0.1:15434/postgres` (local Supabase defaults).

**REST API mode (fallback):**
- Uses `urllib` (stdlib only — no external dependencies).
- Connection from `SUPABASE_URL` + `SUPABASE_KEY` env vars.
- Makes HTTP requests to the Supabase REST API (e.g., `POST /rest/v1/pipeline_jobs`).

**Auto-detection logic (in `__init__`):**
1. If a `SUPABASE_DB_URL` or `PIPELINE_DB_URL` is set → try direct mode.
2. If `SUPABASE_URL` and `SUPABASE_KEY` are set → try REST mode.
3. Otherwise → try local Supabase defaults (`127.0.0.1:15434`).
4. If psycopg2 is not installed → fall back to REST mode if env vars are present.
5. If nothing works → `ensure_connected()` returns `False`.

#### Layer 2: WorkflowHookRecorder (`scripts/ops/workflow_hooks.py`)

Every pipeline script uses the `with hook_recorder.step(...)` context manager. The recorder:

1. **Always writes JSONL** — Appends to `workflow_hooks.jsonl` in the run output directory.
2. **Also writes to Supabase** — If a `PipelineDB` client can be created (via `create_pipeline_db()` factory), it also writes pipeline lifecycle events to the database.

```python
# Auto-connect sequence in workflow_hooks.py
self.db = db or create_pipeline_db()

# create_pipeline_db() factory
def create_pipeline_db() -> PipelineDB | None:
    try:
        db = PipelineDB()
        if db.ensure_connected():
            return db
    except Exception:
        pass
    return None
```

The `_db_emit()` method maps every hook event to the appropriate database operations:

- **Run lifecycle** — First `start` event creates a `pipeline_runs` row; `complete`/`error` events update metrics and status.
- **Job lifecycle** — `start` creates a `pipeline_jobs` row; `complete`/`error` updates the status.
- **Artifact lifecycle** — When a step completes with an `output_path` field, an artifact is recorded using `_ARTIFACT_TYPE_MAP` to determine the type.
- **Config snapshots** — On `training_pipeline` start, the full config is frozen to `pipeline_config_snapshots`.
- **Quality gates** — On `deepeval_run` completion, reads `quality_summary.json` and creates a `dataset_quality_gates` row.
- **Eval sessions** — On `evaluate_pipeline` completion, reads feedback JSON and creates an `eval_sessions` row.

#### Layer 3: Frontend DB Client (`frontend_control/unity-npc-llm-training-dashboard/src/backend/lib/db.ts`)

The dashboard backend connects to the same database via Node.js `pg.Pool`. It reads the same environment variables (`DATABASE_URL`, `SUPABASE_DB_URL`) and falls back to the same localhost defaults (`127.0.0.1:15434`, user `postgres`, password `postgres`).

#### Layer 4: Job Queue (`src/backend/services/job-queue.ts`)

The `JobQueue` class provides a PostgreSQL-backed job queue that:

- **Persists jobs** in the `pipeline_jobs` table (survives server restarts).
- **Polls** for pending jobs every 2 seconds using `FOR UPDATE SKIP LOCKED` — avoids row-level contention.
- **Spawns child processes** with PID tracking.
- **Retries failed jobs** with exponential backoff (2ⁿ × 1s, default max 5 attempts) stored in `metadata->retryCount`.
- **Checks PID liveness** every 10 seconds via `/proc/PID` — marks dead PIDs as "lost".
- **Cancels jobs** via SIGTERM → 30s grace → SIGKILL escalation.
- **Graceful shutdown** — drains running jobs with a configurable timeout, force-kills remaining.
- **Recovers on restart** — finds previously running jobs, checks if their PIDs are alive, and either continues monitoring or marks them as lost.

### What Gets Written Per Stage

| Pipeline Stage | DB Tables Populated | Trigger |
|---------------|-------------------|---------|
| `generate_dataset` | pipeline_jobs, pipeline_runs, pipeline_artifacts | step("generate_dataset") |
| `sanitize_dataset` | pipeline_jobs, pipeline_runs, pipeline_artifacts | step("sanitize_dataset") |
| `dataset_eval` | pipeline_jobs, pipeline_runs, dataset_quality_gates | step("deepeval_run") |
| `train` | pipeline_jobs, pipeline_runs, pipeline_artifacts, pipeline_config_snapshots | step("training_pipeline") |
| `evaluate` | pipeline_jobs, pipeline_runs, eval_sessions | step("evaluate_pipeline") |
| `export` | pipeline_jobs, pipeline_runs, pipeline_artifacts | step("export_gguf") |

All writes are wrapped in try/except — the pipeline never blocks on database failures.

### Auth System

The dashboard has a custom bearer-token auth system built on the `api_keys` and `api_audit_log` tables.

#### Key Generation

The bootstrap script at `scripts/ops/setup_admin_key.py`:

1. Generates a cryptographically secure 64-char hex key via `secrets.token_hex(32)`.
2. Computes a bcrypt hash of the key (cost factor 10).
3. Stores the hash, prefix (first 8 chars), name, and role in the `api_keys` table.
4. Prints the raw key to stdout exactly once — it cannot be retrieved later.

The script prefers Python's `bcrypt` package but falls back to a Node.js subprocess if unavailable.

```bash
python scripts/ops/setup_admin_key.py
# Output: Admin API Key Generated — Key: a1b2c3d4...
```

#### Authentication Flow

The auth middleware (`src/backend/middleware/auth.ts`):

1. Extracts the Bearer token from the `Authorization` header.
2. Takes the first 8 hex characters as the prefix.
3. Queries `api_keys WHERE key_prefix = $1 AND is_active = true` — uses the prefix index for fast lookup.
4. Compares the full key against the bcrypt hash (`bcrypt.compare`).
5. On success, attaches the key metadata (`id`, `role`, `name`) to `req.apiKey`.
6. Updates `last_used_at` in the background.

#### Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access — create/revoke keys, manage all jobs, view all data |
| `operator` | Manage jobs — enqueue, cancel, view runs and artifacts |
| `viewer` | Read-only — blocked on POST/PUT/PATCH/DELETE |

#### Audit Logging

The audit middleware (`src/backend/middleware/audit.ts`) fires on response finish:

- Logs all mutations (POST, PUT, PATCH, DELETE) and errors (status ≥ 400).
- Records method, path, status code, API key ID, user role, IP address, and duration.
- **Redacts sensitive fields** before storing the request body: `password`, `secret`, `key`, `api_key`, `token`, `authorization`, `access_token`, `refresh_token` (and their camelCase variants).
- Truncates request bodies to 2000 characters.
- Fire-and-forget (`.catch()` swallows errors) — never blocks the response.

### Docker Services

When `supabase start` runs, it starts these local services:

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL (Postgres) | 15434 | Main database — all pipeline tables live here |
| Kong API Gateway | 16437 | REST API gateway routing to PostgREST, Auth, Storage, etc. |
| Supabase Studio | 16438 | Web UI for database management, SQL editor, table browsing |
| Edge Runtime | 8081 | Deno runtime for Edge Functions |
| Vector | — | Dedicated vector similarity search (managed internally) |
| ImgProxy | 9000 | Image transformation and optimization |

The project configuration is in `supabase/config.toml`:

```toml
project_id = "Unsloth_Core"

[api]
port = 16437
max_rows = 1000

[db]
port = 15434
major_version = 17

[studio]
port = 16438
api_url = "http://127.0.0.1:16437"

[edge_runtime]
enabled = true
policy = "per_worker"  # Hot reload for local development
deno_version = 2

[realtime]
enabled = true
```

### Edge Functions

One Edge Function is currently deployed:

**`pipeline-status`** (`supabase/functions/pipeline-status/index.ts`):
- Written in TypeScript for Deno, using `@supabase/supabase-js` 2.49.1.
- Queries all 6 pipeline tables in parallel via `Promise.all`.
- Returns a JSON summary: job counts by status, run counts, artifact distribution, average quality gate pass rate, average eval win rate, and a deduplicated list of NPCs.
- Includes CORS headers for cross-origin access.
- Accessible at `http://localhost:16437/functions/v1/pipeline-status`.

Edge Functions use Deno 2 (configured in `config.toml`) with `per_worker` policy for hot-reloading during local development.

### Realtime

Migration `20260521000002` adds 6 pipeline tables to the `supabase_realtime` publication:

```sql
CREATE PUBLICATION supabase_realtime FOR TABLE
    pipeline_jobs,
    pipeline_runs,
    pipeline_artifacts,
    dataset_quality_gates,
    eval_sessions,
    pipeline_config_snapshots;
```

This enables the frontend to subscribe to database changes via Supabase Realtime WebSockets without polling the API. The `useWebSocketQuery` React Query hook in the frontend (`src/hooks/useWebSocketQuery.ts`) bridges these events into React Query's cache invalidation.

---

## 2. Future Ideas

### Short-Term

These are incremental improvements — small effort, high value.

#### Supabase Studio Dashboard

Create a custom dashboard within Supabase Studio (port 16438) for pipeline monitoring. The Studio's SQL editor can run saved queries for:

- Recent job activity: `SELECT * FROM pipeline_jobs ORDER BY created_at DESC LIMIT 20`
- Training success rate: `SELECT npc_key, status, COUNT(*) FROM pipeline_runs GROUP BY npc_key, status`
- Quality gate trends: `SELECT npc_key, pass_rate, created_at FROM dataset_quality_gates ORDER BY created_at DESC`

Saved queries + charts in Studio give non-technical team members visibility without needing the full dashboard.

#### PGAudit Integration

The `pgaudit` extension is already installed (from the Supabase template) but not configured. Enabling it would provide:

- Database-level audit logging of all DDL and DML operations — complements the existing application-level `api_audit_log`.
- Session, object, and role-level audit granularity.
- Writes audit records to the PostgreSQL log.

Configuration would require setting `shared_preload_libraries = 'pgaudit'` in `postgresql.conf` and running `ALTER SYSTEM SET pgaudit.log = 'write,ddl'` — but note that local Supabase instances reset this on restart, so this works best on a hosted Supabase project.

#### Index Optimization with index_advisor

Both `hypopg` and `index_advisor` are available. Running `index_advisor` on slow pipeline queries can recommend better indexes:

```sql
SELECT * FROM index_advisor('SELECT * FROM pipeline_jobs WHERE status = ''pending'' ORDER BY created_at LIMIT 5');
```

This is especially useful for the job queue's polling query and API key prefix lookups.

#### Scheduled Cleanup with pg_cron

Add `pg_cron` to periodically clean up old audit logs and completed jobs:

```sql
-- Requires pg_cron in shared_preload_libraries
SELECT cron.schedule('cleanup-old-logs', '0 3 * * *',
  $$DELETE FROM api_audit_log WHERE created_at < NOW() - INTERVAL '90 days'$$);

SELECT cron.schedule('cleanup-old-jobs', '0 4 * * 0',
  $$DELETE FROM pipeline_jobs WHERE created_at < NOW() - INTERVAL '30 days'
    AND status IN ('completed', 'failed', 'stopped')$$);
```

This needs the `pg_cron` extension enabled (commented out in migration 4) and `shared_preload_libraries = 'pg_cron'` set. For local Supabase this requires a custom PostgreSQL config.

### Medium-Term

These require more effort and span multiple systems.

#### Semantic NPC Memory Search

Use the `vector` extension (already installed at version 0.5.1) with `pg_trgm` for production NPC memory:

- Store player dialogue embeddings in the existing `npc_memories.embedding` column.
- Query with the existing `search_memories_hybrid()` function combining `<=>` cosine similarity and `ts_rank_cd` full-text ranking.
- Fall back to trigram matching (`pg_trgm`) when embeddings are unavailable or similarity scores are low.

This is ready to go — the schema, function, and indexes already exist from migration 2. The missing piece is the embedding pipeline from the Unity runtime.

#### Full Player Profile Population

The `player_profiles`, `dialogue_sessions`, and `dialogue_turns` tables exist but are empty. Population requires:

- Unity runtime posting session data to Supabase REST API.
- Player identification (anonymous or authenticated).
- Dialogue turn logging with NPC and player messages.

The `dialogue_turns` table uses the `embedding` extension for storing both player and NPC message embeddings, enabling future context retrieval.

#### Edge Function Webhooks

Create Edge Functions that trigger on database changes (via Supabase Database Webhooks or the existing Realtime publication):

- On `pipeline_runs` INSERT → POST to a Discord/Slack webhook with run results.
- On `dataset_quality_gates` INSERT with `pass_rate < 0.5` → trigger a regeneration workflow.
- On `eval_sessions` INSERT with `win_rate > 0.6` → flag the candidate for promotion.

#### Pgmq Event-Driven Chaining

Replace the 2-second FOR UPDATE SKIP LOCKED polling loop with `pgmq` LISTEN/NOTIFY for instant job pickup:

- When a new job is inserted, emit a NOTIFY event.
- The job queue wakes immediately instead of waiting for the next poll cycle.
- Requires enabling `pgmq` (commented out in migration 4) and rebuilding the local Docker setup.

#### Backup and Restore

Set up routine backups:

```bash
# Nightly dump
supabase db dump -f backups/pipeline_$(date +%Y%m%d).sql

# Restore
supabase db restore backups/pipeline_20260522.sql
```

The seed file (`supabase/seed.sql`) populates sample NPC profiles and test results after a fresh reset, so the Studio always has data to display.

### Long-Term

These are significant architectural shifts that would replace or fundamentally change how the system operates.

#### Replace Node Backend with Edge Functions

Eliminate the Node.js dashboard server entirely. A pure Supabase-native dashboard would:

- Use a static frontend (React SPA, already exists) talking directly to Supabase REST API.
- Replace backend auth with Supabase Auth (email/password, OAuth providers).
- Use Realtime WebSockets instead of the existing polling + WebSocket bridge.
- Implement pipeline orchestration as Edge Functions triggered by database changes.
- Remove the dependency on Express, `node`, and the dashboard backend entirely.

This would simplify deployment (no Node server to manage) but requires rewriting the job queue and workflow chaining logic in Deno/TypeScript.

#### Player Feedback Loop

Close the loop from runtime to training:

1. Players rate NPC responses in Unity (thumbs up/down, 1–5 stars).
2. Ratings stored in Supabase (`dialogue_turns.rating`).
3. Edge Function analyzes low-rated responses → identifies knowledge gaps.
4. Generates new training examples targeting those gaps.
5. Triggers automated retraining (via pipeline_jobs INSERT).
6. New LoRA adapter promoted to production if it passes evaluation.

This would make NPCs improve continuously based on real player interactions.

#### Multi-User Pipeline

Add team support through Supabase Auth:

- Email/password or OAuth (GitHub, Google) authentication.
- Per-user job queues — queries filtered by `pipeline_jobs.created_by`.
- Personal API keys — each user gets their own set of keys.
- Role-based dashboard views: admin sees everything, operator sees only their NPCs, viewer sees read-only reports.
- Audit log already captures user role and API key ID — the infrastructure is ready.

#### Analytics Dashboard

Create materialized views for pipeline analytics:

```sql
CREATE MATERIALIZED VIEW mv_training_metrics AS
SELECT
  npc_key,
  preset,
  technique,
  COUNT(*) AS run_count,
  AVG((metrics->>'loss')::numeric) AS avg_loss,
  AVG((metrics->>'duration_s')::numeric) AS avg_duration_s
FROM pipeline_runs
WHERE status = 'ok'
GROUP BY npc_key, preset, technique;
```

These materialized views would be refreshed periodically (via pg_cron) and queried by a Grafana dashboard or Supabase Studio charts.

Metrics to track: average training time per NPC, success rate by technique, VRAM usage trends, quality gate pass rate over time, eval win rate by model version.

#### Federated NPC Memory

Shared semantic memory across all Unity clients through Supabase Realtime:

- When player A interacts with an NPC, the memory (with embedding) is written to `npc_memories`.
- All other Unity instances receive the update via Realtime subscription.
- The NPC in player B's session can reference player A's conversation.
- Enables persistent world state — NPCs remember across sessions and players.

This requires careful privacy and data isolation design (which memories are shared, which are per-player) but the technical infrastructure (Realtime, vector search, RLS) is already in place.

#### A/B Test Framework

Route player queries to different LoRA adapter versions via Supabase:

- Store multiple versions of a LoRA adapter in `pipeline_artifacts`.
- Edge Function or REST endpoint routes player queries to version A or B.
- Track win rates via `eval_sessions`-style scoring.
- Auto-promote the winning version when confidence thresholds are met.
- Roll back automatically if the new version underperforms.

This turns the NPC deployment process into a continuous improvement pipeline with data-driven promotion gates.

---

## Quick Reference

### Useful Commands

```bash
# Start/stop local Supabase
supabase start
supabase stop

# Apply migrations
supabase db push

# Reset and re-apply all migrations (destroys data)
supabase db reset

# Generate new migration
supabase migration new add_column_to_pipeline_runs

# Dump/restore
supabase db dump -f backup.sql
supabase db restore backup.sql

# View database status
supabase status

# Generate initial admin API key
python scripts/ops/setup_admin_key.py
```

### Environment Variables

| Variable | Default | Used By |
|----------|---------|---------|
| `SUPABASE_DB_URL` | — | PipelineDB (direct mode), dashboard backend |
| `PIPELINE_DB_URL` | — | PipelineDB override |
| `PIPELINE_DB_HOST` | `127.0.0.1` | PipelineDB connection |
| `PIPELINE_DB_PORT` | `15434` | PipelineDB connection |
| `PIPELINE_DB_USER` | `postgres` | PipelineDB connection |
| `PIPELINE_DB_PASS` | `postgres` | PipelineDB connection |
| `PIPELINE_DB_NAME` | `postgres` | PipelineDB connection |
| `SUPABASE_URL` | `http://127.0.0.1:16437` | PipelineDB (REST mode), Edge Functions |
| `SUPABASE_KEY` | — | PipelineDB (REST mode) |
| `DATABASE_URL` | — | Dashboard backend (pg.Pool) |

### Key Files

| File | Purpose |
|------|---------|
| `supabase/config.toml` | Supabase project configuration |
| `supabase/seed.sql` | Sample data for development |
| `supabase/migrations/*.sql` | All 8 schema migrations |
| `supabase/functions/pipeline-status/index.ts` | Edge Function for pipeline summary |
| `scripts/ops/pipeline_db.py` | Dual-mode PipelineDB client (1,838 lines) |
| `scripts/ops/workflow_hooks.py` | Workflow hook recorder with DB integration |
| `scripts/ops/setup_admin_key.py` | Bootstrap script for initial API key |
| `frontend_control/.../src/backend/lib/db.ts` | Frontend DB client (pg.Pool) |
| `frontend_control/.../src/backend/middleware/auth.ts` | Auth middleware (bcrypt validation) |
| `frontend_control/.../src/backend/middleware/audit.ts` | Audit logging middleware |
| `frontend_control/.../src/backend/services/job-queue.ts` | PostgreSQL-backed job queue (891 lines) |
