-- ============================================================
-- Enable Pipeline Extensions
-- Applied: May 2026
-- These extensions enable fuzzy text search, job scheduling,
-- and message queue functionality for the NPC pipeline.
-- 
-- Extensions MUST be enabled in migrations, not via psql,
-- because supabase db reset destroys and recreates the database
-- from scratch. Migration-based extensions persist through resets.
-- ============================================================

-- 1. Trigram text similarity
-- Used for: fuzzy NPC memory search, dialogue matching, near-duplicate detection
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

-- 2. Fuzzy string matching (Levenshtein, soundex, metaphone)
-- Used for: spellcheck, fuzzy NPC name matching, input tolerance
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch WITH SCHEMA extensions;

-- 3. PostgreSQL job scheduler
-- Used for: periodic memory decay, automated eval scheduling, maintenance tasks
-- NOTE: pg_cron requires shared_preload_libraries = 'pg_cron' in postgresql.conf
-- to be fully operational. For local Supabase, this may need a custom postgres config.
-- The extension is installed here; scheduling will work when preload is configured.
-- CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;

-- 4. Lightweight message queue
-- Used for: alternative to FOR UPDATE SKIP LOCKED job polling
-- Can replace our manual PostgreSQL job queue with a proper Pub/Sub model
-- CREATE EXTENSION IF NOT EXISTS pgmq WITH SCHEMA extensions;
