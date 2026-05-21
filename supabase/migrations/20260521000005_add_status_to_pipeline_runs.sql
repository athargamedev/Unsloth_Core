-- ============================================================
-- Add status column to pipeline_runs for easier querying
-- Applied: May 2026
-- ============================================================

-- Add a dedicated status column (was previously only inside metrics JSONB)
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';

-- Add an index for filtering by status
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs (status);
