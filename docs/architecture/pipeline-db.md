1|# Pipeline Database Integration (Python)
2|
3|## Overview
4|
5|`src/core/ops/pipeline_db.py` provides the `PipelineDB` class (1,837 lines, ~65 methods, 20 public API methods) that lets pipeline scripts write state to the Supabase/PostgreSQL pipeline tables. It supports two connection modes and auto-detects the best available option.
6|
7|## Connection Modes
8|
9|### Direct PostgreSQL (Preferred)
10|Uses `psycopg2` for full CRUD via parameterized SQL. Connection configured via:
11|
12|| Env Variable | Purpose |
13||-------------|---------|
14|| `SUPABASE_DB_URL` | Primary PostgreSQL connection string |
15|| `PIPELINE_DB_URL` | Optional override for DB connection string |
16|| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` | Individual connection params |
17|
18|### REST API Fallback
19|Uses Supabase REST API via `urllib` (stdlib only, no extra dependencies). Connection configured via:
20|
21|| Env Variable | Purpose |
22||-------------|---------|
23|| `SUPABASE_URL` | Base URL for REST API (e.g. `http://localhost:16437`) |
24|| `SUPABASE_KEY` | Anon or service key |
25|
26|### Local Default
27|When neither connection method is configured, the class falls back to:
28|
29|```
30|host=127.0.0.1 port=15434 user=postgres password=postgres dbname=postgres
31|```
32|
33|This matches the defaults of a `supabase start` local instance.
34|
35|## Auto-Detection
36|
37|`create_pipeline_db()` (in `src/core/ops/workflow_hooks.py`) handles auto-detection:
38|
39|```python
40|from scripts.ops.workflow_hooks import create_pipeline_db
41|
42|db = create_pipeline_db()  # Tries env vars → localhost:15434
43|```
44|
45|Priority order:
46|1. `PIPELINE_DB_URL` (explicit override)
47|2. `SUPABASE_DB_URL` (primary connection string)
48|3. `SUPABASE_URL` + `SUPABASE_KEY` (REST API fallback)
49|4. Localhost defaults
50|
51|## Public API Methods
52|
53|### Jobs
54|| Method | Description |
55||--------|-------------|
56|| `create_job(npc_key, type, command_id, command_args, ...)` | Insert new pipeline job |
57|| `update_job_status(job_id, status, exit_code, error, ...)` | Update job state |
58|| `get_job(job_id)` | Fetch a single job |
59|| `list_jobs(npc_key, status, limit, offset)` | List jobs with filters |
60|
61|### Runs
62|| Method | Description |
63||--------|-------------|
64|| `create_run(npc_key, run_id, run_dir, preset, technique, ...)` | Insert training run |
65|| `update_run_metrics(run_id, metrics, loss, ...)` | Update run metrics |
66|| `get_run(run_id)` | Fetch a single run |
67|| `list_runs(npc_key, limit, offset)` | List runs with filters |
68|
69|### Artifacts
70|| Method | Description |
71||--------|-------------|
72|| `create_artifact(npc_key, artifact_type, file_path, ...)` | Record a generated file |
73|| `list_artifacts(npc_key, artifact_type, limit)` | List artifacts with filters |
74|
75|### Quality Gates
76|| Method | Description |
77||--------|-------------|
78|| `create_quality_gate(npc_key, technique, pass_rate, total, passed, failed, ...)` | Record DeepEval gate result |
79|
80|### Eval Sessions
81|| Method | Description |
82||--------|-------------|
83|| `create_eval_session(npc_key, total, baseline_wins, candidate_wins, win_rate, per_concept, ...)` | Record evaluation result |
84|
85|### Config Snapshots
86|| Method | Description |
87||--------|-------------|
88|| `save_config_snapshot(npc_key, preset, technique, full_config, file_path)` | Freeze training config |
89|
90|### Auth
91|| Method | Description |
92||--------|-------------|
93|| `validate_api_key(key)` | Validate an API key against bcrypt hash (used by setup_admin_key.py) |
94|| `log_audit_event(...)` | Insert audit log entry |
95|
96|### Sync
97|| Method | Description |
98||--------|-------------|
99|| `sync_from_filesystem(path)` | Bulk import filesystem artifacts into pipeline tables |
100|
101|Each method has two implementations (e.g. `_direct_create_job` and `_rest_create_job`) auto-selected by the connection mode.
102|
103|## Integration with WorkflowHookRecorder
104|
105|The `WorkflowHookRecorder` class (`src/core/ops/workflow_hooks.py`) integrates with PipelineDB so that every `step()` context manager in pipeline scripts automatically writes to the database:
106|
107|```python
108|from scripts.ops.workflow_hooks import WorkflowHookRecorder, create_pipeline_db
109|
110|db = create_pipeline_db()
111|recorder = WorkflowHookRecorder(
112|    hook_path="outputs/history_guide/runs/run_20260520/workflow_hooks.jsonl",
113|    tool="ucore",
114|    npc_key="history_guide",
115|    db=db,  # Optional DB client
116|)
117|
118|with recorder.step("generate_dataset", spec_path=spec, run_id=run_id) as ctx:
119|    # Pipeline work...
120|    # Auto-writes: pipeline_jobs (on start), pipeline_runs (on start),
121|    # pipeline_artifacts (on complete/error), pipeline_config_snapshots (on training start)
122|    pass
123|```
124|
125|What gets written:
126|- **pipeline_jobs**: Created on `step` entry (`status="start"`), updated on exit (`"complete"` or `"error"`)
127|- **pipeline_runs**: Created alongside jobs, tracks run metadata
128|- **pipeline_artifacts**: Created on step completion with file path, checksum, and size
129|- **pipeline_config_snapshots**: Saved when training steps begin
130|
131|## Best-Effort Writes
132|
133|All database writes are wrapped in `try/except` blocks. Pipeline scripts **never fail** due to a database write error. If Supabase is not running, the pipeline continues without tracking:
134|
135|```python
136|try:
137|    db = create_pipeline_db()
138|    if db and db.ensure_connected():
139|        db.create_job(...)
140|except Exception:
141|    logger.warning("DB write failed — continuing pipeline")
142|```
143|
144|## Column Allowlist
145|
146|Dynamic SQL column names are validated against the `SANITIZE_ALLOWLIST` set to prevent SQL injection:
147|
148|```python
149|SANITIZE_ALLOWLIST: set[str] = {
150|    "status", "progress", "error", "wandb_url", "logs", "name",
151|    "role", "is_active", "key_prefix", "version", "config",
152|    "spec_path", "run_id", "technique", "preset", "base_model",
153|    "npc_key", "category", "score", "pass_rate", "total", "passed",
154|    "failed", "failure_reason", "recommendation", "stage", "model",
155|    "model_id", "duration", "method", "path", "status_code",
156|    "ip_address", "request_body", ...
157|}
158|```
159|
160|Any column name not in this set is rejected before hitting the database.
161|
162|## Migration Management
163|
164|Database schema changes are managed via Supabase migrations in `supabase/migrations/`:
165|
166|```bash
167|# Apply all migrations locally
168|supabase db reset
169|```
170|
171|Migration files are numbered by date and purpose:
172|- `20260512000001_create_npc_dialogue_schema.sql` — Runtime tables
173|- `20260521000001_create_pipeline_tables.sql` — Pipeline tables + functions
174|- `20260521000002_enable_realtime_pipeline.sql` — Realtime publication
175|- `20260521000003_add_spec_path_to_pipeline_runs.sql` — Column additions
176|- `20260521000004_enable_pipeline_extensions.sql` — pg_trgm, fuzzystrmatch
177|- `20260521000005_add_status_to_pipeline_runs.sql` — Status column + index
178|
179|Always add new columns or schema changes via migrations, never via direct psql.
180|