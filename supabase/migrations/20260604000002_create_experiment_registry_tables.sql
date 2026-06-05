-- ============================================================
-- Experiment Registry — Model, Dataset, and Metric tracking
-- Applied: June 2026
-- Database: local Supabase (Unsloth_Core project)
--
-- Three new tables:
--   model_registry     — every adapter/model produced by training
--   dataset_versions   — dataset generation lineage + content hash
--   metric_collections — step-level training metrics (time-series)
-- ============================================================

-- ============================================================
-- 1. MODEL REGISTRY
-- Every exported adapter/GGUF produced by training.
-- One row per artifact, linked to the pipeline_artifacts row.
-- ============================================================
CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    model_name TEXT NOT NULL,                    -- human-readable: "chef_assistant_qwen2.5_lora_r16"
    npc_key TEXT NOT NULL,                       -- which NPC this model was trained for
    base_model TEXT NOT NULL,                    -- e.g. "qwen2.5:7b", "llama3.1:8b"
    technique TEXT NOT NULL,                     -- "lora", "qlora", "full"

    -- Lineage
    training_run_id TEXT,                        -- run_id from pipeline_runs
    dataset_hash TEXT,                           -- SHA256 of training dataset used
    parent_model_id UUID REFERENCES model_registry(id),  -- for fine-tuning chaining

    -- Training config snapshot
    lora_config JSONB DEFAULT '{}',
    training_params JSONB DEFAULT '{}',          -- learning_rate, num_epochs, batch_size, etc.

    -- Evaluation results
    win_rate REAL,                               -- from latest comparison run
    eval_session_id UUID REFERENCES eval_sessions(id),
    quality_gate_pass_rate REAL,                 -- from latest quality gate

    -- Artifact references
    adapter_artifact_id UUID REFERENCES pipeline_artifacts(id),  -- LoRA adapter
    gguf_artifact_id UUID REFERENCES pipeline_artifacts(id),     -- GGUF export
    gguf_quantization TEXT,                      -- "q4_k_m", "q8_0", etc.

    -- Status
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'training', 'ready', 'deployed', 'archived', 'failed')),
    tags TEXT[] DEFAULT '{}',                    -- ["baseline", "candidate", "production", "experiment"]

    -- Metadata
    deployed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_registry_npc ON model_registry(npc_key);
CREATE INDEX IF NOT EXISTS idx_model_registry_status ON model_registry(status);
CREATE INDEX IF NOT EXISTS idx_model_registry_base ON model_registry(base_model);
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_registry_name_npc ON model_registry(npc_key, model_name);

-- ============================================================
-- 2. DATASET VERSIONS
-- Every generation of a dataset, with content hash and lineage.
-- Links forward to model_registry via dataset_hash.
-- ============================================================
CREATE TABLE IF NOT EXISTS dataset_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    npc_key TEXT NOT NULL,
    version TEXT NOT NULL,                       -- semver-like: "1.0.0" or date-based
    content_hash TEXT NOT NULL,                  -- SHA256 of full dataset content

    -- Content metadata
    technique TEXT NOT NULL,                     -- "ollama", "synthetic", "curated"
    row_count INTEGER NOT NULL DEFAULT 0,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    split_info JSONB DEFAULT '{}',               -- {"train": 100, "validation": 20, "test": 10}
    concept_coverage JSONB DEFAULT '{}',          -- {"teaching": 40, "dialogue": 30, ...}

    -- Lineage
    parent_hash TEXT,                            -- content_hash of previous version
    parent_id UUID REFERENCES dataset_versions(id),
    generation_params JSONB DEFAULT '{}',         -- model, temperature, seed, etc.
    change_log TEXT,                             -- "expanded teaching concepts by 20 rows"

    -- Quality metadata
    quality_gate_pass_rate REAL,
    quality_gate_id UUID REFERENCES dataset_quality_gates(id),

    -- Provenance
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraint
    UNIQUE (npc_key, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_dataset_versions_npc ON dataset_versions(npc_key);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_hash ON dataset_versions(content_hash);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_parent ON dataset_versions(parent_hash);

-- ============================================================
-- 3. METRIC COLLECTIONS
-- Step-level training metrics (time-series).
-- One row per logged step per training run.
-- ============================================================
CREATE TABLE IF NOT EXISTS metric_collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Linkage
    run_id TEXT NOT NULL,                        -- run_id from pipeline_runs
    npc_key TEXT NOT NULL,
    job_id UUID REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    model_registry_id UUID REFERENCES model_registry(id),

    -- Step
    step INTEGER NOT NULL,                       -- training step number
    epoch REAL,                                  -- current epoch (float for fractional)

    -- Metrics (at least one should be non-null)
    loss REAL,
    grad_norm REAL,
    learning_rate REAL,
    tokens_per_second REAL,
    gpu_memory_mb REAL,
    gpu_utilization REAL,

    -- Additional metrics stored as key-value
    extra_metrics JSONB DEFAULT '{}',

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraint
    UNIQUE (run_id, step)
);

CREATE INDEX IF NOT EXISTS idx_metric_collections_run ON metric_collections(run_id);
CREATE INDEX IF NOT EXISTS idx_metric_collections_npc ON metric_collections(npc_key);
CREATE INDEX IF NOT EXISTS idx_metric_collections_step ON metric_collections(step);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE IF EXISTS model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS dataset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS metric_collections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS public_all_model_registry ON model_registry;
CREATE POLICY public_all_model_registry ON model_registry
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS public_all_dataset_versions ON dataset_versions;
CREATE POLICY public_all_dataset_versions ON dataset_versions
    FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS public_all_metric_collections ON metric_collections;
CREATE POLICY public_all_metric_collections ON metric_collections
    FOR ALL USING (true) WITH CHECK (true);
