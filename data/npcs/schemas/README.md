Definitive dataset schemas

These JSON schemas are the machine-readable source of truth for dataset record formats:

- sft_record.schema.json
  - For subjects/datasets/{npc_key}/{technique}/train.jsonl and validation.jsonl
  - Requires ChatML messages with at least one user and one assistant message
  - Requires complete metadata: npc_key, technique, split, category, concept, difficulty, source, content_hash, generator_params, safety_tags
  - Active techniques: template, docs, ollama, openai, anthropic

- rl_preferences_record.schema.json
  - For subjects/datasets/{npc_key}/{technique}/rl/preferences.jsonl

- rl_reward_rollout_record.schema.json
  - For subjects/datasets/{npc_key}/{technique}/rl/reward_rollouts.jsonl

Authoritative human-readable contract:
- docs/NPC_DATA_RL_EXECUTION_CONTRACT.md

Generation-readiness check:
- ./ucore validate-spec subjects/NPC_specs/{npc_key}.json --generation-ready
