-- ============================================================
-- Add comparison fields to eval_sessions for structured model-vs-model runs
-- Applied: June 2026
-- ============================================================

-- Human-readable comparison ID (e.g. 20260604_marvel_heroes_instructor_qwen-vs-llama_001)
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS comparison_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_sessions_comparison_id ON eval_sessions(comparison_id) WHERE comparison_id IS NOT NULL;

-- Model identity columns (pulled out of metadata JSONB into typed columns)
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS baseline_model TEXT;
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS candidate_model TEXT;
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS judge_model TEXT;

-- Dataset fingerprint
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS dataset_hash TEXT;
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS dataset_path TEXT;

-- RunRegistry back-references
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS baseline_eval_run_id TEXT;
ALTER TABLE IF EXISTS eval_sessions ADD COLUMN IF NOT EXISTS candidate_eval_run_id TEXT;

-- Add artifact_type 'comparison_report' to pipeline_artifacts check constraint
ALTER TABLE IF EXISTS pipeline_artifacts DROP CONSTRAINT IF EXISTS pipeline_artifacts_artifact_type_check;
ALTER TABLE IF EXISTS pipeline_artifacts ADD CONSTRAINT pipeline_artifacts_artifact_type_check
    CHECK (artifact_type IN (
        'dataset_raw', 'dataset_clean', 'adapter', 'gguf_adapter', 'gguf_full',
        'eval_report', 'feedback_json', 'config_snapshot', 'comparison_report', 'other'
    ));

-- Add 'Compare' type to pipeline_jobs check constraint
ALTER TABLE IF EXISTS pipeline_jobs DROP CONSTRAINT IF EXISTS pipeline_jobs_type_check;
ALTER TABLE IF EXISTS pipeline_jobs ADD CONSTRAINT pipeline_jobs_type_check
    CHECK (type IN ('Dataset', 'Training', 'Evaluation', 'Export', 'Validation', 'Feedback', 'System', 'Pipeline', 'Compare'));

-- Add indexes for the new filtered columns
CREATE INDEX IF NOT EXISTS idx_eval_sessions_baseline_model ON eval_sessions(baseline_model);
CREATE INDEX IF NOT EXISTS idx_eval_sessions_candidate_model ON eval_sessions(candidate_model);

-- Function: upsert_eval_session for idempotent comparison recording
CREATE OR REPLACE FUNCTION upsert_eval_session(
    p_comparison_id TEXT,
    p_npc_key TEXT,
    p_baseline_model TEXT,
    p_candidate_model TEXT,
    p_judge_model TEXT DEFAULT NULL,
    p_dataset_hash TEXT DEFAULT NULL,
    p_dataset_path TEXT DEFAULT NULL,
    p_total_examples INTEGER DEFAULT 0,
    p_baseline_wins INTEGER DEFAULT 0,
    p_candidate_wins INTEGER DEFAULT 0,
    p_ties INTEGER DEFAULT 0,
    p_win_rate REAL DEFAULT NULL,
    p_per_concept JSONB DEFAULT '{}',
    p_weak_concepts TEXT[] DEFAULT '{}',
    p_baseline_eval_run_id TEXT DEFAULT NULL,
    p_candidate_eval_run_id TEXT DEFAULT NULL,
    p_feedback_json_path TEXT DEFAULT NULL,
    p_report_html_path TEXT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'
) RETURNS eval_sessions
LANGUAGE plpgsql
AS $$
DECLARE
    v_result eval_sessions;
BEGIN
    INSERT INTO eval_sessions (
        comparison_id, npc_key, baseline_model, candidate_model, judge_model,
        dataset_hash, dataset_path, total_examples, baseline_wins, candidate_wins,
        ties, win_rate, per_concept, weak_concepts,
        baseline_eval_run_id, candidate_eval_run_id,
        feedback_json_path, report_html_path, metadata
    ) VALUES (
        p_comparison_id, p_npc_key, p_baseline_model, p_candidate_model, p_judge_model,
        p_dataset_hash, p_dataset_path, p_total_examples, p_baseline_wins, p_candidate_wins,
        p_ties, p_win_rate, p_per_concept, p_weak_concepts,
        p_baseline_eval_run_id, p_candidate_eval_run_id,
        p_feedback_json_path, p_report_html_path, p_metadata
    )
    ON CONFLICT (comparison_id) WHERE comparison_id IS NOT NULL
    DO UPDATE SET
        total_examples = EXCLUDED.total_examples,
        baseline_wins = EXCLUDED.baseline_wins,
        candidate_wins = EXCLUDED.candidate_wins,
        ties = EXCLUDED.ties,
        win_rate = EXCLUDED.win_rate,
        per_concept = EXCLUDED.per_concept,
        weak_concepts = EXCLUDED.weak_concepts,
        feedback_json_path = EXCLUDED.feedback_json_path,
        report_html_path = EXCLUDED.report_html_path,
        metadata = EXCLUDED.metadata
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$;
