# Unsloth_Core AI Agent Instructions

## Quick Start
- Activate environment: `source unsloth_env/bin/activate`
- Train: `python scripts/train.py subjects/chemistry_instructor.json --from-spec`
- Validate: Add `--preset smoke` for quick test (10 steps, low VRAM)

## Build & Test Commands
- CLI (Unified): `./ucore <command> [args]` (Replaces individual script calls for common tasks)
- Train: `python scripts/train.py <subject.json> [--preset <preset>] [--from-spec]`
- Generate dataset: `python scripts/generate_dataset.py <subject.json>`
- Sanitize dataset: `python scripts/sanitize_dataset.py <input.jsonl>`
- Smoke test (GGUF): `python scripts/smoke_test.py <model.gguf> --spec <subject.json>`
- Evaluate: `python scripts/evaluate.py --baseline <gguf> --candidate <gguf> --spec <subject.json>`
- Export: `python scripts/export.py <npc_key> --model <model_id>` or `python scripts/export_adapter.py outputs/<npc_key>/`
- Dashboard: `python scripts/dashboard.py`

## Architecture
Four-stage pipeline: Data generation → Sanitization → Training → Export & Validation. Use Unsloth for efficient fine-tuning on consumer GPUs.

### Dataset Generation Structure
1. **Subject Specification**: JSON file in `subjects/` with structure:
   - `npc_key`: Unique snake_case ID (e.g., "chemistry_instructor")
   - `npc_name`: PascalCase display name
   - `identity`: Core personality and background
   - `teaching`: Subject matter expertise
   - `dialogue`: Conversation style
   - `quest`: Interactive scenarios
   - `refusal`: Boundary handling
   - `research_queries`: Array of NotebookLM queries for data generation

2. **Generation Process**:
   - `generate_dataset.py` calls NotebookLM API with research queries
   - Generates Q&A pairs in ChatML format (messages array with role/content)
   - Splits 88% train / 12% validation
   - Outputs: `datasets/{npc_key}/{technique}/train.jsonl` and `datasets/{npc_key}/{technique}/validation.jsonl`
   - Technique is one of `notebooklm`, `ollama`, `template`
   - Configurable via `--technique` flag in `generate_dataset.py`

### Model Training Steps
**Local Training**:
1. Select preset based on model size (see [README.md](README.md) presets table)
2. Run: `python scripts/train.py subjects/{subject}.json --preset {preset}`
3. Config hierarchy: base YAML → preset overrides → CLI flags
4. Outputs LoRA adapter in `outputs/{npc_key}/`

**Remote Training** (Colab):
1. Use notebooks in `colab/outputs/` (e.g., `chemistry_instructor_colab_training.ipynb`)
2. Upload subject JSON and run cells
3. Download trained adapter

**Remote Training** (Kaggle):
1. Set up Kaggle CLI: `pip install kaggle`, configure API key
2. Copy Colab notebook to new dir, modify for Kaggle datasets
3. Create kernel metadata: `kaggle kernels init -p dir/`
4. Push: `kaggle kernels push -p dir/`
5. Run on Kaggle with GPU (up to 9 hours/session)
6. Download GGUF from kernel output

**Training Details**:
- Uses Unsloth SFTTrainer with LoRA (rank 16-64, alpha 16-64)
- Packing enabled for efficiency
- Gradient accumulation for effective batch size ≥8
- Early stopping on validation loss

3. **Export for Unity LLMUnity**
1. **GGUF Export**: `python scripts/export.py <npc_key> --model <model_id> --quantization q4_k_m` → `exports/{npc_key}/{npc_key}-{model_short}-q4_k_m.gguf`
   - Quantized 4-bit for local Unity inference
   - Compatible with llama.cpp backend in LLMUnity
   - Also exports f16 variant for LoRA adapter loading
   - GGUF naming: `{npc_key}-{model_short}-{quant}.gguf` (e.g., `chemistry_instructor-llama3.2-3b-q4_k_m.gguf`)

2. **Adapter Export**: `python scripts/export_adapter.py outputs/{npc_key}/` → safetensors files
   - For cloud inference or further fine-tuning
   - Load with Transformers + PEFT

3. **Smoke Testing**: `python scripts/smoke_test.py exports/{npc_key}/...gguf --spec subjects/{subject}.json`
   - Performs rapid inference tests to ensure persona adherence.
   - Checks for AI artifacts and response quality.

## Unified CLI (`ucore`)
The `ucore` tool provides a streamlined interface for the entire pipeline:
- `./ucore generate subjects/subject.json --ollama`
- `./ucore sanitize datasets/subject/ollama/train.jsonl`
- `./ucore train subjects/subject.json --preset fast-3b`
- `./ucore smoke exports/subject/model.gguf --spec subjects/subject.json`
- `./ucore pipeline subjects/subject.json` (Runs gen -> sanitize -> train -> export in one go)

### Supabase Database
A local Supabase instance is used for backend data storage, player/NPC session state, memory, embeddings, and graph analytics.

Local Docker services:
- PostgreSQL: `supabase_db_Unsloth_Core` on `localhost:15434`
- Studio: `supabase_studio_Unsloth_Core` on `localhost:16438`
- Kong/API gateway: `localhost:16437`

Primary tables:
- `dialogue_sessions` – active/ended player-NPC sessions
- `dialogue_turns` – each player/npc turn text
- `npc_memories` – summarized memories for player/NPC pairs
- `player_profiles` – player metadata
- `npc_profiles` – NPC definitions, personality, voice rules, domain knowledge
- `player_memory_embeddings` – vector embeddings for semantic memory
- `dialogue_turn_embeddings` – embeddings for dialogue turns
- `dialogue_relation_terms` – relation terms for graph matching
- `relation_graph_nodes` / `relation_graph_edges` – relationship graph storage
- `test_results` – evaluation and QA run metadata

Key functions and procedures:
- `get_or_create_session` – open or reuse an active session
- `insert_turn_fast` – add dialogue turns and update session counts
- `summarize_dialogue_session` – summarize an ended session into memory
- `get_player_npc_memory` – retrieve the latest NPC memory summary
- `get_god_memory` – semantic retrieval over memory embeddings
- `search_memories_semantic` – vector similarity search for memories
- `generate_dialogue_relation_graph` – build relationship graphs from dialogue
- `get_dialogue_relation_matches` – find relation terms in conversation
- `upsert_npc_profile` / `get_npc_profile` – manage and retrieve NPC catalog data

Useful Supabase commands:
- `mcp_supabase_apply_migration` – apply schema migrations
- `mcp_supabase_execute_sql` – run raw SQL (use for queries only; keep DDL in migrations)
- `mcp_supabase_generate_typescript_types` – generate client types
- `mcp_supabase_get_advisors` – inspect security/performance issues

## Conventions
- Subject specs: `{topic}_{role}.json` in `subjects/`
- Outputs (LoRA adapters): `outputs/{npc_key}/`
- Exports (GGUF): `exports/{npc_key}/{npc_key}-{model_short}-{quant}.gguf`
- Datasets: `datasets/{npc_key}/{technique}/train.jsonl`
- Eval: `eval/reports/{npc_key}/` and `eval/comparisons/`
- TensorBoard runs: `outputs/{npc_key}/runs/`
- GGUF naming: `{npc_key}-{model}-{quant}.gguf` where model is short form (e.g., `llama3.2-3b`)
- Quantization standard: `q4_k_m`
- Config hierarchy: base YAML < preset dict < CLI overrides
- Models: Must be `-bnb-4bit` format from Unsloth repos
- Colab-trained variants: `outputs/colab/{npc_key}/` and `exports/colab/{npc_key}/`

## Potential Pitfalls
- CUDA OOM: Use `--preset safe-any` (batch=1, seq_len=1024, r=8)
- Model format: Ensure `-bnb-4bit` suffix
- Loss not decreasing: Lower LR to 1e-4, check `train_on_responses_only: true`
- Config issues: Later overrides earlier in hierarchy

## Key Files
- [scripts/train.py](scripts/train.py): Main training script with presets
- [configs/lora-sft-base.yaml](configs/lora-sft-base.yaml): Base config reference
- [subjects/](subjects/): Subject specifications
- [README.md](README.md): Presets table, model guidelines

See [README.md](README.md) for detailed setup and presets.