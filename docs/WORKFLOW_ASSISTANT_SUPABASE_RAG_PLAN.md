# Workflow Assistant Supabase Vector RAG Plan

## Goal

Make the Workflow Assistant an operational copilot that can retrieve grounded project knowledge from local Supabase without becoming an NPC dataset/model. It should answer from code, docs, pipeline artifacts, logs, command schemas, and prior operational lessons while protecting GPU/VRAM resources used by training, evaluation, export, and Ollama generation.

## Current Integration Assessment

### What already exists

- Local Supabase is already a first-class pipeline dependency.
- The modular backend has PostgreSQL access via `src/backend/lib/db.ts` using `pg.Pool` with local defaults:
  - host `127.0.0.1`
  - port `15434`
  - user/password `postgres/postgres`
  - database `postgres`
- Pipeline tables already exist for jobs, runs, artifacts, quality gates, eval sessions, config snapshots, API keys, and audit logs.
- Existing migrations already enable/use vector search for NPC memory:
  - `CREATE EXTENSION IF NOT EXISTS "vector"`
  - `npc_memories.embedding VECTOR(768)`
  - hybrid FTS + vector search through `search_memories_hybrid(...)`
  - memory consolidation/decay helpers.
- The Workflow Assistant backend now has a safe chat/status/load/unload foundation and a resource guard.

### Gaps for Workflow Assistant RAG

- Existing `npc_memories` tables are designed for player/NPC runtime memory, not developer workflow knowledge.
- Reusing `npc_memories` would mix operational assistant knowledge with NPC dialogue state and violate the separation we want.
- There is no codebase/document ingestion pipeline yet.
- There is no assistant-specific source registry, chunk table, embedding job table, or retrieval RPC.
- The assistant currently builds a small filesystem/job context, but does not retrieve semantically relevant project knowledge.

## Design Principle

Create a separate assistant knowledge base in Supabase:

- NPC memory remains for Unity runtime/player dialogue.
- Workflow Assistant memory is for local developer operations.
- Same Supabase/vector infrastructure, separate tables and RPCs.
- Retrieval must be hybrid: vector similarity + PostgreSQL full-text search + metadata filters.
- Every retrieved answer must cite source path/artifact/job/run when possible.

## Proposed Supabase Schema

Add a new migration, for example:

`supabase/migrations/20260529000001_create_workflow_assistant_rag.sql`

### Extensions

```sql
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
```

### Source registry

```sql
CREATE TABLE IF NOT EXISTS assistant_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type TEXT NOT NULL CHECK (source_type IN (
    'code', 'doc', 'config', 'npc_spec', 'reference_doc', 'dataset_summary',
    'quality_gate', 'eval_report', 'workflow_hook', 'job_log', 'command_schema',
    'pipeline_run', 'artifact_manifest', 'lesson'
  )),
  source_uri TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  npc_key TEXT,
  technique TEXT,
  run_id TEXT,
  job_id TEXT,
  content_hash TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assistant_sources_type ON assistant_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_assistant_sources_npc ON assistant_sources(npc_key);
CREATE INDEX IF NOT EXISTS idx_assistant_sources_hash ON assistant_sources(content_hash);
```

### Chunks

Use `VECTOR(768)` initially to align with existing NPC memory schema and local embedding options. If later using a different embedding dimension, add an `embedding_model` column and separate table/version instead of changing old vectors in place.

```sql
CREATE TABLE IF NOT EXISTS assistant_knowledge_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES assistant_sources(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER,
  embedding VECTOR(768),
  fts_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_assistant_chunks_source ON assistant_knowledge_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_assistant_chunks_fts ON assistant_knowledge_chunks USING GIN(fts_vector);
CREATE INDEX IF NOT EXISTS idx_assistant_chunks_embedding ON assistant_knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### Retrieval feedback / self-learning

This is not model fine-tuning. It is operational memory: confirmed fixes, user corrections, useful retrieved sources, bad retrieved sources, and stable workflow lessons.

```sql
CREATE TABLE IF NOT EXISTS assistant_retrieval_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query TEXT NOT NULL,
  selected_npc_key TEXT,
  selected_job_id TEXT,
  retrieved_chunk_ids UUID[] NOT NULL DEFAULT '{}',
  accepted BOOLEAN,
  feedback TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assistant_lessons (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lesson_type TEXT NOT NULL CHECK (lesson_type IN ('preference', 'correction', 'failure', 'fix', 'workflow', 'tool_quirk')),
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source_event_id UUID REFERENCES assistant_retrieval_events(id) ON DELETE SET NULL,
  npc_key TEXT,
  content_hash TEXT NOT NULL,
  embedding VECTOR(768),
  fts_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(content_hash)
);

CREATE INDEX IF NOT EXISTS idx_assistant_lessons_type ON assistant_lessons(lesson_type);
CREATE INDEX IF NOT EXISTS idx_assistant_lessons_fts ON assistant_lessons USING GIN(fts_vector);
CREATE INDEX IF NOT EXISTS idx_assistant_lessons_embedding ON assistant_lessons USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

### Hybrid retrieval RPC

```sql
CREATE OR REPLACE FUNCTION search_assistant_knowledge(
  p_query_text TEXT,
  p_query_embedding VECTOR(768),
  p_match_count INTEGER DEFAULT 10,
  p_match_threshold REAL DEFAULT 0.25,
  p_source_types TEXT[] DEFAULT NULL,
  p_npc_key TEXT DEFAULT NULL,
  p_vector_weight REAL DEFAULT 0.65,
  p_fts_weight REAL DEFAULT 0.35
) RETURNS TABLE(
  chunk_id UUID,
  source_id UUID,
  source_type TEXT,
  source_uri TEXT,
  title TEXT,
  content TEXT,
  npc_key TEXT,
  metadata JSONB,
  similarity REAL,
  fts_rank REAL,
  combined_score REAL
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH vector_matches AS (
    SELECT c.id, 1 - (c.embedding <=> p_query_embedding) AS sim
    FROM assistant_knowledge_chunks c
    JOIN assistant_sources s ON s.id = c.source_id
    WHERE c.embedding IS NOT NULL
      AND (p_source_types IS NULL OR s.source_type = ANY(p_source_types))
      AND (p_npc_key IS NULL OR s.npc_key = p_npc_key)
      AND 1 - (c.embedding <=> p_query_embedding) > p_match_threshold
  ),
  fts_matches AS (
    SELECT c.id, ts_rank_cd(c.fts_vector, plainto_tsquery('english', p_query_text)) AS rank
    FROM assistant_knowledge_chunks c
    JOIN assistant_sources s ON s.id = c.source_id
    WHERE c.fts_vector @@ plainto_tsquery('english', p_query_text)
      AND (p_source_types IS NULL OR s.source_type = ANY(p_source_types))
      AND (p_npc_key IS NULL OR s.npc_key = p_npc_key)
  )
  SELECT
    c.id,
    s.id,
    s.source_type,
    s.source_uri,
    s.title,
    c.content,
    s.npc_key,
    c.metadata || s.metadata,
    COALESCE(vm.sim, 0)::REAL,
    COALESCE(fm.rank, 0)::REAL,
    (COALESCE(vm.sim, 0) * p_vector_weight + COALESCE(fm.rank, 0) * p_fts_weight)::REAL
  FROM assistant_knowledge_chunks c
  JOIN assistant_sources s ON s.id = c.source_id
  LEFT JOIN vector_matches vm ON vm.id = c.id
  LEFT JOIN fts_matches fm ON fm.id = c.id
  WHERE vm.id IS NOT NULL OR fm.id IS NOT NULL
  ORDER BY combined_score DESC
  LIMIT p_match_count;
END;
$$;
```

## Embedding Strategy

### Recommended local-first policy

Use local embeddings by default to avoid external dependency and preserve project privacy.

Good candidates:

1. `nomic-embed-text` through Ollama if available.
   - Easy local API.
   - Avoids Python ML dependency in dashboard backend.
2. Python `sentence-transformers` model if Ollama embedding is unavailable.
   - Good for batch indexing.
   - Use a 768-dimensional model to match current vector schema, or create a dedicated dimension-specific schema.
3. Remote embeddings only as an explicit opt-in profile.

### Resource guard

Embedding should never run during:

- training
- dataset-eval
- Ollama generation
- export
- llama-server evaluation
- feedback loop auto-retrain

Indexing can still scan and hash files while GPU is busy, but embedding calls should pause until `assistant-resource-guard` reports safe state.

## Ingestion Targets

### Stable project knowledge

- `AGENTS.md`
- `README.md`
- `docs/**/*.md`
- `configs/**/*.yaml`
- `subjects/schemas/**/*.json`
- `subjects/NPC_specs/**/*.json`
- `subjects/reference_docs/**/*.md`
- `ucore` help output and command schemas from `/api/command-schemas`
- Dashboard backend route definitions and frontend API types

### Dynamic operational knowledge

- `subjects/datasets/*/*/quality_summary.json`
- `subjects/datasets/*/*/quality_failures.json`
- `outputs/*/runs/**/workflow_hooks.jsonl`
- `eval/reports/**/*.{md,json,html}` summarized/extracted
- `eval/results/**/*.{json,md}`
- `exports/**` manifests/checksums, not binary GGUF contents
- `.runtime/registry.json` as state, not long-term knowledge
- job logs, capped and chunked by error/warning/stage

### Exclude

- `node_modules/`
- `.git/`
- `wandb/` raw logs except selected summaries
- binary models / GGUFs / safetensors
- `.deepeval/` runtime internals
- raw large datasets unless summarized; store dataset profiles and failure rows, not every generated training row by default

## Backend Additions

### Services

Add under `frontend_control/unity-npc-llm-training-dashboard/src/backend/services/`:

- `assistant-embeddings.ts`
  - `embedText(text): Promise<number[]>`
  - provider: Ollama `/api/embeddings` or `/api/embed`
  - config-driven model name
- `assistant-indexer.ts`
  - scans known sources
  - computes hashes
  - chunks content
  - upserts `assistant_sources` and `assistant_knowledge_chunks`
  - skips unchanged sources
- `assistant-retriever.ts`
  - embeds query
  - calls `search_assistant_knowledge(...)`
  - returns cited chunks
- `assistant-learning.ts`
  - records retrieval events
  - promotes user-confirmed corrections/fixes to `assistant_lessons`

### Routes

Add to `routes/assistant.ts`:

- `GET /api/assistant/rag/status`
  - DB available, vector extension available, source/chunk counts, last indexed time
- `POST /api/assistant/rag/index`
  - start an indexing job through the job queue or guarded background task
- `POST /api/assistant/rag/search`
  - debug/search endpoint for retrieved chunks
- `POST /api/assistant/rag/feedback`
  - accept/reject retrieved answer and optional correction

### Chat integration

Update `runAssistantChat(...)` flow:

1. Collect live context (current implementation).
2. Retrieve RAG chunks using query + selected NPC/job/run filters.
3. Build prompt with:
   - live state
   - top retrieved chunks with source citations
   - relevant lessons/corrections
4. Ask local LLM only if resource guard allows.
5. If LLM blocked, deterministic fallback still includes retrieved evidence.
6. Store retrieval event with chunk IDs.

## Chunking Rules

- Markdown/docs: split by heading, then cap chunks around 700–1200 tokens.
- Code: chunk by exported functions/classes/routes; include file path and line range.
- JSON/YAML configs: chunk by top-level keys.
- Logs: chunk by stage and error window; do not embed entire verbose logs.
- HTML reports: strip to text and preserve report metadata/path.
- JSONL hooks: chunk by trace/run summary plus error events.

## Self-Learning Model

Self-learning should mean retrieval memory, not autonomous code mutation or fine-tuning.

Allowed:

- Remember user-approved fixes.
- Remember repeated failures and successful recovery commands.
- Track which retrieved chunks were useful.
- Promote stable lessons into `assistant_lessons`.
- Prefer high-value sources in future retrieval.

Not allowed without explicit user confirmation:

- Editing code.
- Changing dataset thresholds.
- Bypassing quality gates.
- Fine-tuning assistant model.
- Writing into NPC memory tables.

## UI Additions

Add a Workflow Assistant RAG panel section:

- DB/vector status badge.
- Last indexed timestamp.
- Source counts by type.
- “Index project knowledge” button.
- “Pause indexing during heavy jobs” indicator.
- Retrieved sources expandable under each assistant answer.
- Feedback buttons: Useful / Not useful / Save as lesson.

## Implementation Phases

### Phase 1 — DB foundation

- Add assistant RAG migration.
- Add health checks for vector extension and table counts.
- Add `GET /api/assistant/rag/status`.

### Phase 2 — Local embedding + indexer

- Implement Ollama embedding provider.
- Add config to `workflow_assistant/assistant_config.json`:

```json
{
  "rag": {
    "enabled": true,
    "embeddingProvider": "ollama",
    "embeddingModel": "nomic-embed-text",
    "embeddingDimension": 768,
    "chunkTokenTarget": 900,
    "maxRetrievedChunks": 8
  }
}
```

- Implement hash-based source scanning and upsert.
- Index docs/specs/configs first.

### Phase 3 — Retrieval in chat

- Add retriever and citations.
- Inject retrieved chunks into assistant prompt.
- Add deterministic fallback with retrieval evidence.

### Phase 4 — Logs/results RAG

- Index quality summaries/failures.
- Index workflow hooks and eval reports.
- Add job-specific retrieval filters.

### Phase 5 — Self-learning feedback

- Add retrieval event logging.
- Add lesson promotion endpoint.
- Include lessons in retrieval.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Assistant competes for VRAM | Reuse resource guard; pause embeddings/LLM during heavy jobs |
| Stale code/docs in RAG | content hash + last indexed timestamp + stale source status |
| Bad self-learning pollution | require explicit user confirmation before lesson promotion |
| Mixing NPC memory and assistant memory | separate tables and RPCs |
| Embedding dimension mismatch | store embedding model/dimension; version schema if changing dimensions |
| Huge logs/datasets blow up DB | summarize/filter/chunk only relevant evidence |
| Hallucinated commands | always include command schemas and `ucore --help` indexed chunks |

## Recommended Next Step

Implement Phase 1 and Phase 2 as a small vertical slice:

1. Migration for `assistant_sources`, `assistant_knowledge_chunks`, `assistant_retrieval_events`, `assistant_lessons`, and `search_assistant_knowledge`.
2. `assistant-embeddings.ts` with Ollama provider.
3. `assistant-indexer.ts` indexing `AGENTS.md`, `README.md`, `docs/**/*.md`, `subjects/NPC_specs/**/*.json`, and `subjects/reference_docs/**/*.md`.
4. `GET /api/assistant/rag/status` and `POST /api/assistant/rag/index`.
5. Test with a query like: “why is training blocked for history_guide?” and verify retrieved sources cite quality gate rules and relevant artifacts.
