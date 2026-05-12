# Project Structure & Workflow Refactoring

## Outcome

Transform Unsloth_Core into a professional multi-workflow training platform with structured workflow documentation, experiment tracking via run IDs, YAML-based preset system, TensorBoard-integrated evaluation, and a modern frontend for managing and tracking the entire training lifecycle.

## Context

The project trains NPC (non-player character) personas via Unsloth LoRA fine-tuning. Current state:

- **4 NPCs trained** (chemistry_instructor, bible_instructor, marvel_instructor, world_map_guide) + 1 `default/` test artifact
- **Configs duplicated**: Training presets live both as a hardcoded Python dict in `scripts/train.py` AND as separate YAML files in `configs/`
- **No experiment tracking**: Outputs go directly to `outputs/{npc_key}/` without run IDs, making it impossible to compare different training runs on the same NPC
- **Minimal documentation**: Only `docs/OLLAMA_WORKFLOW.md` exists — no workflow docs for notebooklm, template, training, or evaluation
- **Basic dashboard**: `scripts/dashboard.py` is a bare FastAPI+Jinja2 app with no SPA, no real-time training charts, no run comparison
- **Subject specs inconsistent**: `subjects/*.json` files have a flat structure that doesn't match AGENTS.md documented fields (identity, teaching, dialogue, quest, refusal, research_queries)
- **No eval reports generated yet**: `eval/` directory exists but is empty
- **No version control**: Project has no git repo

## Constraints

- Must NOT break existing trained adapters (`outputs/{npc_key}/adapter_model.safetensors`) or GGUF exports (`exports/{npc_key}/*.gguf`)
- Must NOT break the training pipeline — training commands must still work identically
- Must remain compatible with RTX 3060 6GB VRAM constraints
- Must preserve the config hierarchy: base YAML → preset overrides → CLI overrides
- Must keep backward compatibility for existing script invocations where feasible
- All `_config/paths.py` helper functions must remain functional

## Non-Goals

- Adding new NPC personas (separate content goal)
- Rewriting Unsloth or TRL training internals
- Cloud deployment or CI/CD pipeline
- Changing GGUF export format or LLMUnity compatibility
- Performance optimization of training loop itself
- Full React/Angular/Vue build toolchain — prefer lightweight approach (HTMX + Alpine.js)

## Ask Before

- Removing or renaming any existing `outputs/{npc_key}/` directories (trained adapters)
- Changing the `_config/paths.py` public API (other scripts import it)
- Deleting the `default/` output (confirm it's a test artifact first)
- Moving or restructuring `subjects/*.json` schema (affects AGENTS.md documentation)
- Introducing new Python or Node.js dependencies
- Any destructive file operations on trained artifacts
- Switching from lightweight frontend approach (HTMX) to full SPA framework

## Done Means

The project has: (1) comprehensive workflow docs for all 5 pipeline stages, (2) YAML-only presets, (3) run ID-stamped experiment tracking, (4) professional evaluation with TensorBoard integration and run comparison, (5) a modern dashboard frontend showing configs, runs, live metrics, and comparisons, (6) standardized subject specs, (7) clean git repo. All existing trained artifacts remain loadable.
