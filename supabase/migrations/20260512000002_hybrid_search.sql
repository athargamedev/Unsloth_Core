-- ============================================================
-- Hybrid Search for NPC Memories
-- Combines Vector Similarity with Full-Text Search
-- ============================================================

-- 1. Add search vector to npc_memories for faster FTS
ALTER TABLE npc_memories ADD COLUMN IF NOT EXISTS fts_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS idx_npc_memories_fts ON npc_memories USING GIN(fts_vector);

-- 2. Hybrid search function using Reciprocal Rank Fusion (RRF) logic or weighted sum
CREATE OR REPLACE FUNCTION search_memories_hybrid(
    p_player_id UUID,
    p_npc_id TEXT,
    p_query_text TEXT,
    p_query_embedding VECTOR(768),
    p_match_threshold REAL DEFAULT 0.3,
    p_match_count INTEGER DEFAULT 10,
    p_fts_weight REAL DEFAULT 0.5,
    p_vector_weight REAL DEFAULT 0.5
) RETURNS TABLE(
    id UUID,
    content TEXT,
    memory_type TEXT,
    importance REAL,
    similarity REAL,
    fts_rank REAL,
    combined_score REAL
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH vector_matches AS (
        SELECT 
            nm.id,
            1 - (nm.embedding <=> p_query_embedding) AS sim
        FROM npc_memories nm
        WHERE nm.player_id = p_player_id
          AND nm.npc_id = p_npc_id
          AND nm.embedding IS NOT NULL
          AND 1 - (nm.embedding <=> p_query_embedding) > p_match_threshold
    ),
    fts_matches AS (
        SELECT 
            nm.id,
            ts_rank_cd(nm.fts_vector, plainto_tsquery('english', p_query_text)) AS rank
        FROM npc_memories nm
        WHERE nm.player_id = p_player_id
          AND nm.npc_id = p_npc_id
          AND nm.fts_vector @@ plainto_tsquery('english', p_query_text)
    )
    SELECT
        nm.id,
        nm.content,
        nm.memory_type,
        nm.importance,
        COALESCE(vm.sim, 0)::REAL AS similarity,
        COALESCE(fm.rank, 0)::REAL AS fts_rank,
        (COALESCE(vm.sim, 0) * p_vector_weight + COALESCE(fm.rank, 0) * p_fts_weight)::REAL AS combined_score
    FROM npc_memories nm
    LEFT JOIN vector_matches vm ON nm.id = vm.id
    LEFT JOIN fts_matches fm ON nm.id = fm.id
    WHERE (vm.id IS NOT NULL OR fm.id IS NOT NULL)
    ORDER BY combined_score DESC
    LIMIT p_match_count;
END;
$$;
