-- ============================================================
-- Pipeline State Management — Jobs, Runs, Artifacts, Eval
-- Applied: May 2026
-- Database: local Supabase (Unsloth_Core project)
--
-- Replaces the in-memory registry.json job tracking with
-- persistent tables. .pipeline/runs.jsonl will be deprecated
-- in favor of these tables.
-- ============================================================

-- ============================================================
-- 1. PIPELINE JOBS
-- Persistent job queue — every command execution creates a row.
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_key TEXT NOT NULL,
    type TEXT NOT NULL
        CHECK (type IN ('Dataset', 'Training', 'Evaluation', 'Export', 'Validation', 'Feedback', 'System', 'Pipeline')),
    command_id TEXT NOT NULL,
    command_args JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'stopped', 'paused')),
    progress INTEGER NOT NULL DEFAULT 0
        CHECK (progress >= 0 AND progress <= 100),
    loss REAL,
    exit_code INTEGER,
    error TEXT,
    wandb_url TEXT,
    workflow_id TEXT,
    chain_next JSONB,
    logs TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status ON pipeline_jobs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_npc ON pipeline_jobs(npc_key);
CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_created ON pipeline_jobs(created_at DESC);

-- ============================================================
-- 2. PIPELINE RUNS
-- Training run metadata — one row per training execution.
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    npc_key TEXT NOT NULL,
    run_id TEXT NOT NULL,
    run_dir TEXT NOT NULL,
    preset TEXT,
    model_id TEXT,
    technique TEXT,
    base_model TEXT,
    config_snapshot JSONB DEFAULT '{}',
    metrics JSONB DEFAULT '{}',
    lora_config JSONB DEFAULT '{}',
    wandb_enabled BOOLEAN DEFAULT FALSE,
    wandb_url TEXT,
    has_adapter BOOLEAN DEFAULT FALSE,
    has_tensorboard BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    UNIQUE(npc_key, run_id)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_npc ON pipeline_runs(npc_key);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created ON pipeline_runs(created_at DESC);

-- ============================================================
-- 3. PIPELINE ARTIFACTS
-- Track all generated files — datasets, adapters, GGUF exports.
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_key TEXT NOT NULL,
    run_id TEXT,
    job_id UUID REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    artifact_type TEXT NOT NULL
        CHECK (artifact_type IN ('dataset_raw', 'dataset_clean', 'adapter', 'gguf_adapter', 'gguf_full', 'eval_report', 'feedback_json', 'config_snapshot', 'other')),
    technique TEXT,
    file_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    file_hash TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_npc ON pipeline_artifacts(npc_key);
CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_type ON pipeline_artifacts(artifact_type);

-- ============================================================
-- 4. DATASET QUALITY GATES
-- DeepEval quality gate results — one row per evaluation run.
-- ============================================================
CREATE TABLE IF NOT EXISTS dataset_quality_gates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_key TEXT NOT NULL,
    technique TEXT NOT NULL,
    job_id UUID REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    dataset_path TEXT,
    judge_model TEXT DEFAULT 'qwen3:latest',
    total_samples INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    pass_rate REAL NOT NULL DEFAULT 0.0,
    metrics JSONB DEFAULT '{}',
    categories JSONB DEFAULT '{}',
    failures JSONB DEFAULT '[]',
    failures_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quality_gates_npc ON dataset_quality_gates(npc_key);
CREATE INDEX IF NOT EXISTS idx_quality_gates_created ON dataset_quality_gates(created_at DESC);

-- ============================================================
-- 5. EVAL SESSIONS
-- Side-by-side evaluation results — win/loss per concept.
-- ============================================================
CREATE TABLE IF NOT EXISTS eval_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_key TEXT NOT NULL,
    baseline_artifact_id UUID REFERENCES pipeline_artifacts(id),
    candidate_artifact_id UUID REFERENCES pipeline_artifacts(id),
    total_examples INTEGER NOT NULL DEFAULT 0,
    baseline_wins INTEGER NOT NULL DEFAULT 0,
    candidate_wins INTEGER NOT NULL DEFAULT 0,
    ties INTEGER NOT NULL DEFAULT 0,
    win_rate REAL,
    per_concept JSONB DEFAULT '{}',
    weak_concepts TEXT[] DEFAULT '{}',
    feedback_json_path TEXT,
    report_html_path TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_sessions_npc ON eval_sessions(npc_key);
CREATE INDEX IF NOT EXISTS idx_eval_sessions_created ON eval_sessions(created_at DESC);

-- ============================================================
-- 6. PIPELINE CONFIG SNAPSHOTS
-- Frozen training configurations — immutable record.
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_config_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_key TEXT NOT NULL,
    preset TEXT,
    technique TEXT,
    full_config JSONB NOT NULL,
    file_path TEXT,
    hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_config_snapshots_npc ON pipeline_config_snapshots(npc_key);

-- ============================================================
-- 7. API KEYS
-- API key authentication for dashboard and pipeline access.
-- ============================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'default',
    role TEXT NOT NULL DEFAULT 'admin'
        CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- ============================================================
-- 8. API AUDIT LOG
-- Audit trail for all mutation requests.
-- ============================================================
CREATE TABLE IF NOT EXISTS api_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    user_role TEXT,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER,
    request_body TEXT,
    ip_address TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_path ON api_audit_log(path);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON api_audit_log(created_at DESC);

-- ============================================================
-- FUNCTIONS
-- ============================================================

-- upsert_pipeline_job: insert or update a pipeline job.
-- If a pending/running job exists for the same npc_key and
-- command_id, updates it; otherwise inserts a new row.
CREATE OR REPLACE FUNCTION upsert_pipeline_job(
    p_npc_key TEXT,
    p_type TEXT,
    p_command_id TEXT,
    p_command_args JSONB DEFAULT '[]'
) RETURNS pipeline_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_existing pipeline_jobs;
    v_result pipeline_jobs;
BEGIN
    -- Check for an existing pending or running job for this npc + command
    SELECT * INTO v_existing
    FROM pipeline_jobs
    WHERE npc_key = p_npc_key
      AND command_id = p_command_id
      AND status IN ('pending', 'running')
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_existing.id IS NOT NULL THEN
        -- Update the existing job
        UPDATE pipeline_jobs
        SET command_args = p_command_args,
            status = 'pending',
            updated_at = NOW()
        WHERE id = v_existing.id
        RETURNING * INTO v_result;
    ELSE
        -- Insert a new job
        INSERT INTO pipeline_jobs (npc_key, type, command_id, command_args)
        VALUES (p_npc_key, p_type, p_command_id, p_command_args)
        RETURNING * INTO v_result;
    END IF;

    RETURN v_result;
END;
$$;

-- complete_pipeline_job: mark a job as completed, failed, or stopped.
CREATE OR REPLACE FUNCTION complete_pipeline_job(
    p_job_id UUID,
    p_status TEXT,
    p_exit_code INTEGER DEFAULT NULL,
    p_error TEXT DEFAULT NULL
) RETURNS pipeline_jobs
LANGUAGE plpgsql
AS $$
DECLARE
    v_result pipeline_jobs;
BEGIN
    UPDATE pipeline_jobs
    SET status = p_status,
        exit_code = p_exit_code,
        error = p_error,
        finished_at = NOW(),
        updated_at = NOW()
    WHERE id = p_job_id
    RETURNING * INTO v_result;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline job not found: %', p_job_id;
    END IF;

    RETURN v_result;
END;
$$;

-- insert_pipeline_artifact: record a generated file.
-- file_size_bytes is passed as parameter or left null;
-- the application layer is responsible for resolving the
-- actual file size since pg_stat_file requires superuser.
CREATE OR REPLACE FUNCTION insert_pipeline_artifact(
    p_npc_key TEXT,
    p_run_id TEXT DEFAULT NULL,
    p_artifact_type TEXT,
    p_file_path TEXT,
    p_technique TEXT DEFAULT NULL,
    p_job_id UUID DEFAULT NULL,
    p_file_size_bytes BIGINT DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'
) RETURNS pipeline_artifacts
LANGUAGE plpgsql
AS $$
DECLARE
    v_result pipeline_artifacts;
BEGIN
    INSERT INTO pipeline_artifacts (
        npc_key, run_id, artifact_type, file_path,
        technique, job_id, file_size_bytes, metadata
    ) VALUES (
        p_npc_key, p_run_id, p_artifact_type, p_file_path,
        p_technique, p_job_id, p_file_size_bytes, p_metadata
    ) RETURNING * INTO v_result;

    RETURN v_result;
END;
$$;

-- ============================================================
-- ROW LEVEL SECURITY
-- Open policies for now — restrict once auth is implemented.
-- ============================================================
ALTER TABLE IF EXISTS pipeline_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pipeline_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS dataset_quality_gates ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS eval_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS pipeline_config_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS api_audit_log ENABLE ROW LEVEL SECURITY;

-- Temporary open policies — replace with role-based policies after auth setup
CREATE POLICY IF NOT EXISTS public_all_pipeline_jobs ON pipeline_jobs
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_pipeline_runs ON pipeline_runs
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_pipeline_artifacts ON pipeline_artifacts
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_quality_gates ON dataset_quality_gates
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_eval_sessions ON eval_sessions
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_config_snapshots ON pipeline_config_snapshots
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_api_keys ON api_keys
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY IF NOT EXISTS public_all_audit_log ON api_audit_log
    FOR ALL USING (true) WITH CHECK (true);

-- Note: .pipeline/runs.jsonl tracking will be deprecated
-- once pipeline_jobs and pipeline_runs tables are populated
-- by all pipeline scripts.
