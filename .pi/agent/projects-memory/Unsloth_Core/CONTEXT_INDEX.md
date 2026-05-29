# Context Index

Use this as a pointer file; canonical truth remains in repo files.

## Must-Read Sources

- `AGENTS.md` — agent instructions and current project map.
- `README.md` — human overview.
- `docs/TRAINING_WORKFLOW_CONTEXT.md` — detailed pipeline.
- `subjects/reference_docs/README.md` — primer/reference-doc contract.
- `docs/NPC_DATA_RL_EXECUTION_CONTRACT.md` — RL data contract.

## Core Code Areas

- `ucore` — unified CLI entry point.
- `scripts/dataset/` — generation, sanitization, dataset gate.
- `scripts/training/` — train and feedback loop.
- `scripts/evaluation/` — model evaluation.
- `scripts/export/` — GGUF export.
- `scripts/ops/` — preflight, workflow hooks, DB, admin key.
- `src/backend/` — modular Express backend.
- `frontend_control/`, `src/components/`, `src/hooks/`, `src/stores/` — dashboard.
- `supabase/migrations/` — database schema.

## Search Strategy

- Use `rg`/`find` for short code discovery.
- Use `ctx_batch_execute` for multi-command research or large outputs.
- Use `ctx_execute_file` for large JSONL/log/coverage/output analysis.
- Use `read` before edits so exact text replacements are possible.
