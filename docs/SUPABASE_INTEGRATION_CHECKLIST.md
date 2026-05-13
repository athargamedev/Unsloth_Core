# Supabase Integration Reliability Checklist

Purpose
Validate that a trained/exported NPC in Unsloth_Core is compatible with Unity runtime data flows in Supabase.

## Command

```bash
./ucore supabase-check --npc-key chemistry_instructor
```

Optional:

```bash
# Only check npc_profiles alignment
./ucore supabase-check --npc-key chemistry_instructor --skip-probe

# Use explicit probe player UUID
./ucore supabase-check --npc-key chemistry_instructor --player-id 11111111-1111-1111-1111-111111111111
```

## What it checks

1) Subject + export resolution
- Confirms `subjects/{npc_key}.json` exists
- Resolves latest `exports/{npc_key}/*.gguf`

2) NPC profile alignment (`npc_profiles`)
- Calls `upsert_npc_profile` with:
  - `p_npc_id = npc_key`
  - display name from subject spec
  - description from spec identity block
  - `p_lora_path` from latest GGUF path

3) Runtime dialogue + memory path (probe)
- Calls `get_or_create_session`
- Calls `insert_turn_fast` for a player turn and npc turn
- Calls `summarize_dialogue_session`
- Calls `get_player_npc_memory` and verifies memory text exists

## Required env

- `SUPABASE_URL`
- `SUPABASE_KEY`

## PASS criteria

- upsert succeeds
- session/turn writes succeed
- memory summary can be retrieved via `get_player_npc_memory`

## Notes

- Probe creates a small ended session and memory summary in Supabase.
- This is a reliability harness, not a model-quality evaluation.
