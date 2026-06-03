---
name: unsloth-core-context-maintenance
description: Use when Unsloth_Core context, docs, AGENTS.md, .codex references, skills, or memory look stale, contradictory, too large, or confused by other agent folders.
---

# Unsloth_Core Context Maintenance

Goal: keep Codex from mixing `.codex`, `.hermes`, `.agents`, old docs, and global memory.

## Source Order

1. Live repo/tool output.
2. `AGENTS.md`.
3. `.codex/references/*`.
4. `docs/project-state.md` and `docs/training-workflow.md`.
5. `.hermes/*` and `.agents/*` as reference/migration material.
6. Global memory only after verification if facts can drift.

## Standard Audit

```bash
python src/core/ops/context_audit.py
./ucore --help
./ucore audit check
./ucore strategy --profile npc-production-grounded
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

## Fix Order

1. Actual repo/tool state.
2. `docs/project-state.md`.
3. `AGENTS.md`.
4. `.codex/references/*`.
5. `.codex/skills/*`.
6. `.hermes/*` only if user asks or repo policy requires it.
7. Global memory only when user explicitly asks to update memory.

## Stale Patterns

Flag before trusting:

- NotebookLM as current production path when `AGENTS.md` says no.
- Inactive NPCs marked active.
- Template data presented as production-ready.
- `qwen3:latest` as confirmed local default without fresh benchmark.
- Adapter GGUF evaluated without base model when base+LoRA is required.
- Old path families such as `subjects/`, `outputs/`, or `exports/` if current repo command/docs use `data/` and `artifacts/`.
- Long historical run dumps in agent entrypoints.

## Reporting

Use:

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```

