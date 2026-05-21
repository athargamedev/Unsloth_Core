-- Add spec_path column to pipeline_runs for tracking the NPC spec used (b6)
ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS spec_path TEXT;

-- pipeline_runs is missing updated_at — the REST create_run sends it
ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
-- Ensure updated_at is set to NOW() for existing rows so NOT NULL isn't broken later
UPDATE pipeline_runs SET updated_at = created_at WHERE updated_at IS NULL;

-- Also add to jobs for consistency
ALTER TABLE IF EXISTS pipeline_jobs ADD COLUMN IF NOT EXISTS spec_path TEXT;
