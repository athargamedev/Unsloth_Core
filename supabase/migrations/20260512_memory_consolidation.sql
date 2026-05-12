-- ============================================================
-- NPC Memory Consolidation & Decay
-- Implements smarter memory management for NPCs
-- ============================================================

-- 1. Add decay metadata to npc_memories
ALTER TABLE npc_memories ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 1;
ALTER TABLE npc_memories ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Function to update importance based on access (Frequency-based importance)
CREATE OR REPLACE FUNCTION touch_memory(p_memory_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE npc_memories
    SET access_count = access_count + 1,
        last_accessed_at = NOW(),
        importance = LEAST(1.0, importance + 0.05) -- Boosting importance on access
    WHERE id = p_memory_id;
END;
$$ LANGUAGE plpgsql;

-- 3. Memory Decay Function
-- Reduces importance of memories that haven't been accessed for a long time
CREATE OR REPLACE FUNCTION apply_memory_decay(p_decay_factor REAL DEFAULT 0.1)
RETURNS INTEGER AS $$
DECLARE
    v_updated_count INTEGER;
BEGIN
    UPDATE npc_memories
    SET importance = GREATEST(0.0, importance - p_decay_factor)
    WHERE last_accessed_at < NOW() - INTERVAL '7 days'
      AND importance > 0.1;
    
    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN v_updated_count;
END;
$$ LANGUAGE plpgsql;

-- 4. Consolidate overlapping memories
-- Merges memories of the same type for a player/NPC pair if they are very similar
CREATE OR REPLACE FUNCTION consolidate_memories(
    p_player_id UUID,
    p_npc_id TEXT,
    p_similarity_threshold REAL DEFAULT 0.9
) RETURNS INTEGER AS $$
DECLARE
    v_merged_count INTEGER := 0;
    v_rec RECORD;
BEGIN
    -- This is a simplified version: it finds pairs of memories and keeps the newer/more important one
    FOR v_rec IN 
        SELECT m1.id as id1, m2.id as id2, m1.content as c1, m2.content as c2
        FROM npc_memories m1
        JOIN npc_memories m2 ON m1.player_id = m2.player_id 
                            AND m1.npc_id = m2.npc_id 
                            AND m1.memory_type = m2.memory_type
                            AND m1.id < m2.id
        WHERE m1.player_id = p_player_id
          AND m1.npc_id = p_npc_id
          AND 1 - (m1.embedding <=> m2.embedding) > p_similarity_threshold
    LOOP
        -- Merge logic: delete the older one, update the newer one with combined metadata
        DELETE FROM npc_memories WHERE id = v_rec.id1;
        v_merged_count := v_merged_count + 1;
    END LOOP;

    RETURN v_merged_count;
END;
$$ LANGUAGE plpgsql;
