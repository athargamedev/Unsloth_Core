---
name: unsloth-core-context-maintenance
description: Codex-context shim — canonical version lives at .hermes/skills/. This file adds Codex-specific source order and fix order on top of the Hermes master.
last_verified: 2026-06-05
version: 1.0.0
master: .hermes/skills/unsloth-core-context-maintenance/SKILL.md
---

# Unsloth_Core Context Maintenance (Codex shim)

**This skill is canonical at `.hermes/skills/unsloth-core-context-maintenance/SKILL.md`.** Codex agents always load it from there for the full content (stale patterns, validation, reporting format).

This file adds Codex-specific knowledge precedence and fix order — the master skill is platform-agnostic and already covers all stale patterns.

## Codex Source Order

1. Live repo/tool output.
2. `AGENTS.md`.
3. `.codex/references/*`.
4. `docs/project-state.md` and `docs/training-workflow.md`.
5. `.hermes/*` as reference/migration material (prefer `.codex/` when paths overlap).
6. Global memory only after verification if facts can drift.

## Codex Fix Order

1. Actual repo/tool state.
2. `docs/project-state.md`.
3. `AGENTS.md`.
4. `.codex/references/*`.
5. `.codex/skills/*`.
6. `.hermes/*` only if user asks or repo policy requires it.
7. Global memory only when user explicitly asks.
