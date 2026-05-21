-- ============================================================
-- Enable Realtime for pipeline tables
-- Applied: May 2026
--
-- The frontend subscribes to these publications for live
-- dashboard updates without polling the API.
--
-- Note: On Supabase, the supabase_realtime publication is
-- managed by the Realtime server and may already exist.
-- We drop and recreate it to include our pipeline tables.
-- ============================================================

DROP PUBLICATION IF EXISTS supabase_realtime;

CREATE PUBLICATION supabase_realtime FOR TABLE
    pipeline_jobs,
    pipeline_runs,
    pipeline_artifacts,
    dataset_quality_gates,
    eval_sessions,
    pipeline_config_snapshots;
