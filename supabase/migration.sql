-- ============================================================
-- NPC Dialogue System — Complete Schema
-- Applied: May 2026
-- Database: local Supabase (Unsloth_Core project)
-- ============================================================

-- 1. Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- 2. PLAYER MANAGEMENT
-- ============================================================
CREATE TABLE player_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_name TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT UNIQUE,
    auth_provider TEXT DEFAULT 'local',
    auth_provider_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_player_profiles_email ON player_profiles(email);
CREATE INDEX idx_player_profiles_auth ON player_profiles(auth_provider, auth_provider_id);

-- ============================================================
-- 3. NPC PROFILES (matches Unity SupabaseConfig.cs defaults)
-- ============================================================
CREATE TABLE npc_profiles (
    npc_id TEXT PRIMARY KEY,
    npc_name TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    lora_path TEXT DEFAULT '',
    lora_weight REAL DEFAULT 1.0,
    subject_spec JSONB DEFAULT '{}',
    voice_rules TEXT DEFAULT '',
    domain_knowledge TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 4. DIALOGUE SESSIONS
-- ============================================================
CREATE TABLE dialogue_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID REFERENCES player_profiles(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL REFERENCES npc_profiles(npc_id) ON DELETE CASCADE,
    session_type TEXT DEFAULT 'dialogue',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'ended', 'archived')),
    turn_count INTEGER NOT NULL DEFAULT 0,
    summary TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dialogue_sessions_player ON dialogue_sessions(player_id);
CREATE INDEX idx_dialogue_sessions_npc ON dialogue_sessions(npc_id);
CREATE INDEX idx_dialogue_sessions_status ON dialogue_sessions(status);
CREATE INDEX idx_dialogue_sessions_active
    ON dialogue_sessions(player_id, npc_id, status)
    WHERE status = 'active';

-- ============================================================
-- 5. DIALOGUE TURNS
-- ============================================================
CREATE TABLE dialogue_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES dialogue_sessions(id) ON DELETE CASCADE,
    player_id UUID REFERENCES player_profiles(id) ON DELETE SET NULL,
    npc_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('player', 'npc', 'system', 'god')),
    content TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dialogue_turns_session ON dialogue_turns(session_id);
CREATE INDEX idx_dialogue_turns_npc ON dialogue_turns(npc_id);
CREATE INDEX idx_dialogue_turns_player ON dialogue_turns(player_id);
CREATE INDEX idx_dialogue_turns_created ON dialogue_turns(created_at);

-- ============================================================
-- 6. NPC CHAT HISTORY (matches Unity NPCLoraAgent expectations)
-- ============================================================
CREATE TABLE npc_chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'god')),
    content TEXT NOT NULL,
    player_id UUID REFERENCES player_profiles(id) ON DELETE SET NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_npc_chat_history_npc ON npc_chat_history(npc_id);
CREATE INDEX idx_npc_chat_history_session ON npc_chat_history(session_id);
CREATE INDEX idx_npc_chat_history_created ON npc_chat_history(created_at);

-- ============================================================
-- 7. NPC MEMORIES (summarized cross-session)
-- ============================================================
CREATE TABLE npc_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    session_id UUID REFERENCES dialogue_sessions(id) ON DELETE SET NULL,
    memory_type TEXT NOT NULL DEFAULT 'summary'
        CHECK (memory_type IN ('summary', 'event', 'preference', 'fact', 'relationship', 'other')),
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(player_id, npc_id, memory_type, session_id)
);

CREATE INDEX idx_npc_memories_player ON npc_memories(player_id);
CREATE INDEX idx_npc_memories_npc ON npc_memories(npc_id);
CREATE INDEX idx_npc_memories_type ON npc_memories(memory_type);

-- HNSW index requires pgvector with valid dimension. Skip if no data yet.
-- CREATE INDEX idx_npc_memories_embedding ON npc_memories
--     USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);

-- ============================================================
-- 8. EMBEDDINGS STORAGE
-- ============================================================
CREATE TABLE player_memory_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
    npc_id TEXT,
    content TEXT NOT NULL,
    source_table TEXT NOT NULL DEFAULT 'dialogue_turns',
    source_row_id UUID,
    embedding VECTOR(768) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_player_memory_embeddings_player ON player_memory_embeddings(player_id);
CREATE INDEX idx_player_memory_embeddings_npc ON player_memory_embeddings(npc_id);

CREATE TABLE dialogue_turn_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id UUID REFERENCES dialogue_turns(id) ON DELETE CASCADE,
    session_id UUID REFERENCES dialogue_sessions(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    role TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dialogue_turn_embeddings_session ON dialogue_turn_embeddings(session_id);

-- ============================================================
-- 9. RELATION GRAPH
-- ============================================================
CREATE TABLE dialogue_relation_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    term TEXT NOT NULL,
    context TEXT DEFAULT '',
    frequency INTEGER DEFAULT 1,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(player_id, npc_id, term)
);

CREATE INDEX idx_relation_terms_player ON dialogue_relation_terms(player_id);
CREATE INDEX idx_relation_terms_npc ON dialogue_relation_terms(npc_id);

CREATE TABLE relation_graph_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    node_type TEXT NOT NULL CHECK (node_type IN ('player', 'npc', 'concept', 'event', 'location')),
    label TEXT NOT NULL,
    attributes JSONB DEFAULT '{}',
    embedding VECTOR(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_graph_nodes_player ON relation_graph_nodes(player_id);
CREATE INDEX idx_graph_nodes_npc ON relation_graph_nodes(npc_id);

CREATE TABLE relation_graph_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID NOT NULL REFERENCES player_profiles(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    source_node_id UUID NOT NULL REFERENCES relation_graph_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES relation_graph_nodes(id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL DEFAULT 'related',
    weight REAL DEFAULT 1.0,
    attributes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_graph_edges_player ON relation_graph_edges(player_id);
CREATE INDEX idx_graph_edges_npc ON relation_graph_edges(npc_id);
CREATE UNIQUE INDEX idx_graph_edges_unique ON relation_graph_edges(source_node_id, target_node_id, edge_type);

-- ============================================================
-- 10. TEST RESULTS
-- ============================================================
CREATE TABLE test_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    npc_id TEXT NOT NULL,
    test_name TEXT NOT NULL,
    test_type TEXT DEFAULT 'qa',
    prompt_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    expected_response TEXT,
    score REAL,
    metrics JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_test_results_npc ON test_results(npc_id);
CREATE INDEX idx_test_results_name ON test_results(test_name);

-- ============================================================
-- FUNCTIONS
-- ============================================================

-- get_or_create_session: find active session or create new one
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_player_id UUID,
    p_npc_id TEXT,
    p_session_type TEXT DEFAULT 'dialogue'
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_session_id UUID;
BEGIN
    -- Check for an active session
    SELECT id INTO v_session_id
    FROM dialogue_sessions
    WHERE player_id = p_player_id
      AND npc_id = p_npc_id
      AND status = 'active'
    ORDER BY last_active_at DESC
    LIMIT 1;

    -- Create new if none found
    IF v_session_id IS NULL THEN
        INSERT INTO dialogue_sessions (player_id, npc_id, session_type)
        VALUES (p_player_id, p_npc_id, p_session_type)
        RETURNING id INTO v_session_id;
    ELSE
        -- Touch last_active_at
        UPDATE dialogue_sessions
        SET last_active_at = NOW()
        WHERE id = v_session_id;
    END IF;

    RETURN v_session_id;
END;
$$;

-- insert_turn_fast: add a turn and update session count
CREATE OR REPLACE FUNCTION insert_turn_fast(
    p_session_id UUID,
    p_player_id UUID,
    p_npc_id TEXT,
    p_role TEXT,
    p_content TEXT,
    p_tokens_used INTEGER DEFAULT 0,
    p_latency_ms INTEGER DEFAULT 0
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_turn_id UUID;
    v_turn_number INTEGER;
BEGIN
    -- Get next turn number
    SELECT COALESCE(MAX(turn_number), 0) + 1 INTO v_turn_number
    FROM dialogue_turns
    WHERE session_id = p_session_id;

    -- Insert the turn
    INSERT INTO dialogue_turns (
        session_id, player_id, npc_id, turn_number,
        role, content, tokens_used, latency_ms
    ) VALUES (
        p_session_id, p_player_id, p_npc_id, v_turn_number,
        p_role, p_content, p_tokens_used, p_latency_ms
    ) RETURNING id INTO v_turn_id;

    -- Update session turn count and timestamp
    UPDATE dialogue_sessions
    SET turn_count = turn_count + 1,
        last_active_at = NOW()
    WHERE id = p_session_id;

    RETURN v_turn_id;
END;
$$;

-- summarize_dialogue_session: end session and store summary as memory
CREATE OR REPLACE FUNCTION summarize_dialogue_session(
    p_session_id UUID,
    p_summary TEXT,
    p_importance REAL DEFAULT 0.5
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_session dialogue_sessions;
    v_memory_id UUID;
BEGIN
    -- Get session info
    SELECT * INTO v_session
    FROM dialogue_sessions
    WHERE id = p_session_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Session not found: %', p_session_id;
    END IF;

    -- Update session summary and end it
    UPDATE dialogue_sessions
    SET summary = p_summary,
        status = 'ended',
        ended_at = NOW()
    WHERE id = p_session_id;

    -- Save as NPC memory
    INSERT INTO npc_memories (
        player_id, npc_id, session_id,
        memory_type, content, importance
    ) VALUES (
        v_session.player_id, v_session.npc_id, p_session_id,
        'summary', p_summary, p_importance
    ) RETURNING id INTO v_memory_id;

    RETURN v_memory_id;
END;
$$;

-- get_player_npc_memory: latest memory summary for a player/NPC pair
CREATE OR REPLACE FUNCTION get_player_npc_memory(
    p_player_id UUID,
    p_npc_id TEXT
) RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_content TEXT;
BEGIN
    SELECT content INTO v_content
    FROM npc_memories
    WHERE player_id = p_player_id
      AND npc_id = p_npc_id
      AND memory_type = 'summary'
    ORDER BY updated_at DESC
    LIMIT 1;

    RETURN v_content;
END;
$$;

-- search_memories_semantic: vector similarity search over NPC memories
CREATE OR REPLACE FUNCTION search_memories_semantic(
    p_player_id UUID,
    p_npc_id TEXT,
    p_query_embedding VECTOR(768),
    p_match_threshold REAL DEFAULT 0.7,
    p_match_count INTEGER DEFAULT 5
) RETURNS TABLE(
    id UUID,
    content TEXT,
    memory_type TEXT,
    importance REAL,
    similarity REAL
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        nm.id,
        nm.content,
        nm.memory_type,
        nm.importance,
        1 - (nm.embedding <=> p_query_embedding) AS similarity
    FROM npc_memories nm
    WHERE nm.player_id = p_player_id
      AND nm.npc_id = p_npc_id
      AND nm.embedding IS NOT NULL
      AND 1 - (nm.embedding <=> p_query_embedding) > p_match_threshold
    ORDER BY nm.embedding <=> p_query_embedding
    LIMIT p_match_count;
END;
$$;

-- get_god_memory: semantic retrieval across all memories (GOD/omniscient mode)
CREATE OR REPLACE FUNCTION get_god_memory(
    p_player_id UUID,
    p_query_embedding VECTOR(768),
    p_match_threshold REAL DEFAULT 0.6,
    p_match_count INTEGER DEFAULT 10
) RETURNS TABLE(
    id UUID,
    npc_id TEXT,
    content TEXT,
    memory_type TEXT,
    similarity REAL
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        nm.id,
        nm.npc_id,
        nm.content,
        nm.memory_type,
        1 - (nm.embedding <=> p_query_embedding) AS similarity
    FROM npc_memories nm
    WHERE nm.player_id = p_player_id
      AND nm.embedding IS NOT NULL
      AND 1 - (nm.embedding <=> p_query_embedding) > p_match_threshold
    ORDER BY nm.embedding <=> p_query_embedding
    LIMIT p_match_count;
END;
$$;

-- generate_dialogue_relation_graph: build/update relation graph from dialogue
CREATE OR REPLACE FUNCTION generate_dialogue_relation_graph(
    p_session_id UUID
) RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_player_id UUID;
    v_npc_id TEXT;
    v_terms TEXT[];
    v_term TEXT;
    v_concept_id UUID;
    v_count INTEGER := 0;
BEGIN
    SELECT player_id, npc_id INTO v_player_id, v_npc_id
    FROM dialogue_sessions
    WHERE id = p_session_id;

    -- Extract relation terms from turn content (simple keyword extraction)
    FOR v_term IN
        SELECT DISTINCT regexp_split_to_table(
            lower(content), E'\\W+'
        ) AS word
        FROM dialogue_turns
        WHERE session_id = p_session_id
          AND length(content) > 3
          AND content !~ '^\d+$'
        LIMIT 20
    LOOP
        -- Upsert the term
        INSERT INTO dialogue_relation_terms (player_id, npc_id, term)
        VALUES (v_player_id, v_npc_id, v_term)
        ON CONFLICT (player_id, npc_id, term)
        DO UPDATE SET frequency = dialogue_relation_terms.frequency + 1,
                      last_used_at = NOW();

        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

-- get_dialogue_relation_matches: find relation terms matching input text
CREATE OR REPLACE FUNCTION get_dialogue_relation_matches(
    p_player_id UUID,
    p_npc_id TEXT,
    p_input_text TEXT
) RETURNS TABLE(
    term TEXT,
    context TEXT,
    frequency INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT dt.term, dt.context, dt.frequency
    FROM dialogue_relation_terms dt
    WHERE dt.player_id = p_player_id
      AND dt.npc_id = p_npc_id
      AND p_input_text ILIKE '%' || dt.term || '%'
    ORDER BY dt.frequency DESC;
END;
$$;

-- upsert_npc_profile: insert or update an NPC profile
CREATE OR REPLACE FUNCTION upsert_npc_profile(
    p_npc_id TEXT,
    p_npc_name TEXT DEFAULT NULL,
    p_display_name TEXT DEFAULT NULL,
    p_description TEXT DEFAULT NULL,
    p_system_prompt TEXT DEFAULT NULL,
    p_lora_path TEXT DEFAULT NULL,
    p_lora_weight REAL DEFAULT NULL,
    p_metadata JSONB DEFAULT NULL
) RETURNS npc_profiles
LANGUAGE plpgsql
AS $$
DECLARE
    v_result npc_profiles;
BEGIN
    INSERT INTO npc_profiles (npc_id, npc_name, display_name, description,
                              system_prompt, lora_path, lora_weight, metadata)
    VALUES (
        p_npc_id,
        COALESCE(p_npc_name, p_npc_id),
        COALESCE(p_display_name, p_npc_id),
        COALESCE(p_description, ''),
        COALESCE(p_system_prompt, ''),
        COALESCE(p_lora_path, ''),
        COALESCE(p_lora_weight, 1.0),
        COALESCE(p_metadata, '{}')
    )
    ON CONFLICT (npc_id) DO UPDATE SET
        npc_name = COALESCE(p_npc_name, npc_profiles.npc_name),
        display_name = COALESCE(p_display_name, npc_profiles.display_name),
        description = COALESCE(p_description, npc_profiles.description),
        system_prompt = COALESCE(p_system_prompt, npc_profiles.system_prompt),
        lora_path = COALESCE(p_lora_path, npc_profiles.lora_path),
        lora_weight = COALESCE(p_lora_weight, npc_profiles.lora_weight),
        metadata = CASE WHEN p_metadata IS NOT NULL THEN p_metadata ELSE npc_profiles.metadata END,
        updated_at = NOW()
    RETURNING * INTO v_result;

    RETURN v_result;
END;
$$;

-- get_npc_profile: retrieve an NPC profile by ID
CREATE OR REPLACE FUNCTION get_npc_profile(
    p_npc_id TEXT
) RETURNS npc_profiles
LANGUAGE plpgsql
AS $$
DECLARE
    v_result npc_profiles;
BEGIN
    SELECT * INTO v_result
    FROM npc_profiles
    WHERE npc_id = p_npc_id;

    RETURN v_result;
END;
$$;

-- Enable Row Level Security for all tables
ALTER TABLE player_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE npc_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE npc_chat_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE npc_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_memory_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_turn_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_relation_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE relation_graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE relation_graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_results ENABLE ROW LEVEL SECURITY;

-- RLS: allow public access for Unity client operations
CREATE POLICY public_select_npc_profiles ON npc_profiles
    FOR SELECT USING (true);
CREATE POLICY public_insert_npc_profiles ON npc_profiles
    FOR INSERT WITH CHECK (true);
CREATE POLICY public_update_npc_profiles ON npc_profiles
    FOR UPDATE USING (true) WITH CHECK (true);

CREATE POLICY public_select_chat_history ON npc_chat_history
    FOR SELECT USING (true);
CREATE POLICY public_insert_chat_history ON npc_chat_history
    FOR INSERT WITH CHECK (true);
CREATE POLICY public_delete_chat_history ON npc_chat_history
    FOR DELETE USING (true);

-- Service role and anon access for all other tables
CREATE POLICY public_all_dialogue_sessions ON dialogue_sessions
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_dialogue_turns ON dialogue_turns
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_npc_memories ON npc_memories
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_player_profiles ON player_profiles
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_embeddings ON player_memory_embeddings
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_turn_embeddings ON dialogue_turn_embeddings
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_relation_terms ON dialogue_relation_terms
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_graph_nodes ON relation_graph_nodes
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_graph_edges ON relation_graph_edges
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY public_all_test_results ON test_results
    FOR ALL USING (true) WITH CHECK (true);
