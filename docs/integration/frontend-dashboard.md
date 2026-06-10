1|# Frontend Control Dashboard
2|
3|The Frontend Control Dashboard is the web control plane for Unsloth_Core training workflows. It provides:
4|- Pipeline orchestration for `./ucore` commands
5|- Deep observability (including externally started jobs)
6|- Resilient realtime updates via WebSocket-to-React-Query bridge
7|- Schema-driven command launch forms with validation
8|- Auth-protected API with role-based access control
9|
10|## Architecture
11|
12|```
13|Frontend (React + Vite + Tailwind)
14|    │
15|    ├── Zustand Store (UI state: tabs, filters, toasts, selection)
16|    ├── React Query (11 query hooks + 6 mutations, staleTime=5s)
17|    ├── WebSocket Bridge (useWebSocketQuery: invalidates query caches)
18|    └── Components (30+ components: TrainingSuite, OperationsMatrix, etc.)
19|    │
20|    ▼ HTTP / WebSocket
21|    │
22|Backend (Modular Express, port 3100)
23|    │
24|    ├── API Routes (12 route modules under /api/)
25|    ├── Auth Middleware (Bearer token, bcrypt, RBAC)
26|    ├── Audit Middleware (fire-and-forget to api_audit_log)
27|    ├── Job Queue (PostgreSQL, FOR UPDATE SKIP LOCKED)
28|    └── Registry (in-memory + filesystem artifact sync)
29|    │
30|    ▼
31|PostgreSQL (local Supabase, port 15434)
32|    ├── Pipeline Tables (jobs, runs, artifacts, etc.)
33|    └── Runtime Tables (npc_profiles, dialogue_sessions, etc.)
34|```
35|
36|## Key Components
37|
38|### State Management
39|
40|Dashboard state is divided between two systems:
41|
42|**React Query (Server State)** — 11 query hooks + 6 mutations:
43|- `useJobsQuery()` — Full job state snapshot, polls every 5s
44|- `useTelemetryQuery()` — GPU metrics, polls every 10s
45|- `useSystemStatusQuery()`, `useHealthCheckQuery()` — Backend health
46|- `useDatasetsQuery()`, `useSubjectListQuery()` — Dataset management
47|- `useRunArtifactsQuery()`, `useExportArtifactsQuery()` — Artifact listing
48|- `usePresetsQuery()` — Training presets
49|- `useQualitySummaryQuery()` — DeepEval quality results
50|- `usePipelineStateQuery()`, `useNpcStatusQuery()` — Pipeline state
51|- `useOllamaStatusQuery()`, `useOllamaModelsQuery()` — Ollama management
52|- `useSupabaseStatusQuery()`, `useSupabaseLeaderboardQuery()` — Supabase
53|- `useWatchLogsQuery()` — Filesystem log alerts
54|
55|**Zustand (UI State)** — Persisted locally:
56|- Active tab, selected job IDs, filters
57|- Training config (spec, preset, technique, hyperparameters)
58|- Toast/notification queue (auto-dismiss, type-colored, read state)
59|- Global search recent queries (localStorage-persisted)
60|- Dataset view filter (NPC + technique)
61|
62|### WebSocket Bridge
63|
64|The `useWebSocketQuery` hook connects WebSocket events to React Query caches:
65|- `telemetry` events → `setQueryData` (no network round-trip)
66|- `job_update` events → `invalidateQueries` (triggers fresh fetch)
67|- `logs_cleared` events → invalidate log caches
68|
69|This eliminates polling for telemetry (most latency-sensitive) and provides instant UI updates on job state changes.
70|
71|### NotificationCenter
72|
73|A bell-icon dropdown showing toast notifications:
74|- **Type-colored**: info (accent), success (green), warning (amber), error (red)
75|- **Auto-dismiss**: 8 seconds, with manual dismiss
76|- **Read state**: Unread badge count on bell icon
77|- **Clear all**: Mark all as read
78|- **Limit**: Shows latest 50 toasts
79|
80|### GlobalSearch
81|
82|Ctrl+K opens a modal search across 5 categories:
83|- **NPCs** (Hash icon), **Datasets** (Database icon), **Runs** (Cpu icon)
84|- **Exports** (Package icon), **Jobs** (Play icon)
85|
86|Features:
87|- Keyboard navigation (arrow keys + Enter)
88|- Recent searches (localStorage-persisted, 20 item limit)
89|- Fetches all data on first open, caches for session
90|- Routes to relevant dashboard tab on selection
91|
92|### Keyboard Shortcuts
93|
94|| Shortcut | Action |
95||----------|--------|
96|| `Ctrl+K` | Open global search |
97|| `Ctrl+S` | Stop all running jobs |
98|| `Alt+1-4` | Switch tabs |
99|| `Ctrl+R` | Refresh all data |
100|| `Escape` | Close modals/dropdowns |
101|
102|All shortcuts are input-aware — they are ignored when an input/textarea/select is focused.
103|
104|## API Endpoints
105|
106|All endpoints are prefixed with `/api/`. Auth is required for all `/api/*` paths (enforced by `optionalAuth` middleware in `src/backend/index.ts`).
107|
108|### Job & Pipeline Endpoints
109|
110|| Endpoint | Auth | Description |
111||----------|------|-------------|
112|| `GET /api/jobs` | required | Full job list (cache-refreshed) |
113|| `GET /api/jobs/state` | required | Jobs + workflow metadata snapshot |
114|| `GET /api/jobs/:id/logs` | required | Per-job log file tail |
115|| `POST /api/jobs/clear` | required | Clear all completed jobs |
116|| `POST /api/jobs/sync` | required | Force sync external artifacts |
117|| `POST /api/commands/start` | required | Start a command from the UI |
118|| `POST /api/pipeline` | required | Full pipeline orchestration |
119|| `POST /api/workflow` | required | Multi-step workflow chaining |
120|
121|### Auth Endpoints
122|
123|| Endpoint | Auth | Description |
124||----------|------|-------------|
125|| `GET /api/auth/keys` | admin | List all API keys |
126|| `POST /api/auth/keys` | admin | Create new API key |
127|| `DELETE /api/auth/keys/:id` | admin | Revoke an API key |
128|
129|### System Endpoints
130|
131|| Endpoint | Auth | Description |
132||----------|------|-------------|
133|| `GET /api/health` | none | Health check |
134|| `GET /api/telemetry` | required | GPU/system telemetry |
135|| `GET /api/events?since=<id>` | required | WebSocket event replay fallback |
136|| `GET /api/available-commands` | optional | List available CLI commands |
137|| `GET /api/command-schemas` | optional | Command payload schemas |
138|
139|### Data Endpoints
140|
141|| Endpoint | Auth | Description |
142||----------|------|-------------|
143|| `GET /api/datasets` | optional | List generated datasets |
144|| `GET /api/exports` | required | List exported GGUFs |
145|| `POST /api/exports` | required | Export a trained model |
146|| `POST /api/training` | required | Launch a training run |
147|| `POST /api/eval` | required | Launch an evaluation |
148|
149|### Infrastructure Endpoints
150|
151|| Endpoint | Auth | Description |
152||----------|------|-------------|
153|| `GET /api/ollama` | required | Ollama status and model list |
154|| `GET /api/supabase` | required | Supabase connection status |
155|
156|## Dashboard Tabs
157|
158|The main navigation provides these tabs:
159|
160|1. **Training Suite** — Configure and launch training runs (spec, preset, technique, hyperparameters, W&B toggle)
161|2. **Operations Matrix** — Pipeline stage overview with job table, W&B links, per-NPC status
162|3. **Dataset Pipeline** — Generate, sanitize, and gate datasets with quality reports
163|4. **Eval Reports** — Side-by-side model evaluation results and HTML reports
164|5. **System Hub** — GPU telemetry, Supabase connection, Ollama management, health checks
165|6. **Feedback Loop** — Knowledge gap analysis and auto-retrain orchestration
166|7. **Colab Notebooks** — Integration with Google Colab-based training
167|8. **Leaderboard** — NPC evaluation scores across the 4 active NPCs
168|
169|## Workflow Assistant
170|
171|The dashboard includes a local Ollama-powered workflow assistant that provides contextual guidance without interfering with pipeline operations.
172|
173|### Safety Architecture
174|
175|The assistant is designed with **6 safety layers** to guarantee it never harms generation, training, or evaluation:
176|
177|1. **Resource Guard** (`assistant-resource-guard.ts`): Blocks LLM calls when any GPU-heavy job is active (train, pipeline, dataset-eval, generate-ollama, export, evaluate, feedback). Falls back to deterministic state summaries.
178|2. **Immediate Unload** (`keep_alive: "0s"`): All config profiles tell Ollama to immediately unload the assistant model after each response, freeing VRAM for pipeline work.
179|3. **Shell Execution Blocked**: The `/api/assistant/execute` endpoint returns HTTP 403. Commands are "proposed" only — the user must launch them through the dashboard command modal.
180|4. **Read-Only Context**: The context collector reads filesystem and registry state but never writes. No pipeline artifacts are modified.
181|5. **System Prompt Boundaries**: Priority #1 in the system prompt explicitly prohibits concurrent GPU work.
182|6. **NPC Key Inference**: Uses snake_case pattern matching (requires underscore) to avoid phantom NPC key lookups from casual English words.
183|
184|### Config Profiles
185|
186|Three profiles in `workflow_assistant/assistant_config.json`:
187|
188|| Profile | Model | Context | GPU Layers | Use Case |
189||---------|-------|---------|------------|----------|
190|| `balanced_idle` (default) | `qwen3:latest` | 8192 | full | Normal operation when GPU is idle |
191|| `fast_safe` | `qwen2.5:3b` | 8192 | full | Lightweight queries |
192|| `cpu_fallback` | `qwen2.5:3b` | 4096 | 0 | CPU-only when GPU is fully occupied |
193|
194|### Assistant API Endpoints
195|
196|| Endpoint | Method | Description |
197||----------|--------|-------------|
198|| `/api/assistant/status` | GET | Model profile, resource state, mode (ready/paused) |
199|| `/api/assistant/chat` | POST | Chat with context-aware LLM (or deterministic fallback) |
200|| `/api/assistant` | POST | Backward-compatible alias for chat |
201|| `/api/assistant/load` | POST | Pre-warm the assistant model (blocked during GPU-heavy jobs) |
202|| `/api/assistant/unload` | POST | Unload the assistant model to free VRAM |
203|| `/api/assistant/execute` | POST | **Always returns 403** — shell execution disabled |
204|
205|### Data Validation
206|
207|All dashboard panels use Zod runtime schema validation integrated into React Query `queryFn` hooks. API responses are parsed through Zod schemas before reaching components, preventing silent crashes from malformed backend data. Panels using this pattern:
208|
209|- `EvalReportsPanel.tsx` — Gold standard reference implementation
210|- `FeedbackLoopPanel.tsx` — Feedback result and gap schemas
211|- `EvalWorkflowPanel.tsx` — Eval report schemas with `refetchInterval` polling
212|- `DatasetPipelinePanel.tsx` — Quality summary and failure schemas
213|
214|## Job Queue Integration
215|
216|The dashboard manages jobs through the PostgreSQL-backed `JobQueue` class:
217|- Jobs survive server restarts
218|- Process lifecycle managed with PID tracking (SIGTERM → SIGKILL)
219|- Exponential backoff retry (2^n * 1s, max 5 attempts)
220|- Concurrent job limit configurable (default: 2 on RTX 3060)
221|- Stats tracked incrementally (full recount every 50 transitions)
222|
223|The `JobQueue` and the in-memory `Registry` coexist — the registry tracks legacy and filesystem-discovered jobs; the job queue is the authoritative source for newly created jobs.
224|
225|## Running the Dashboard
226|
227|```bash
228|# Development (Vite dev server + modular backend)
229|cd src/dashboard/unity-npc-llm-training-dashboard
230|npm run dev
231|# → http://localhost:3100
232|
233|# Production (serve built static files)
234|npm run build
235|npm run start:modular
236|
237|# Bootstrap auth
238|python src/core/ops/setup_admin_key.py
239|```
240|
241|### Environment Variables
242|
243|```env
244|PORT=3100
245|DATABASE_URL=postgresql://postgres:***@localhost:15434/postgres
246|GEMINI_API_KEY=your_key_here
247|```
248|
249|## Notes
250|
251|- All `/api/*` requests require a valid Bearer token (except `/api/health` and public-read endpoints)
252|- Bootstrap the first admin key with `python src/core/ops/setup_admin_key.py`
253|- If GPU telemetry is empty, verify `nvidia-smi` is available in PATH
254|- If ports are in use, stop duplicate server instances before restart
255|- Dashboard coexists with terminal-driven workflows — external work appears via sync/artifact discovery
256|- The modular backend (`npm run dev`) replaces the legacy `server.ts`; run `npm run start:modular` for production
257|