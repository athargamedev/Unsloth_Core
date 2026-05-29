# Unsloth_Core Project Memory

Purpose: compact, durable project context for Pi agents working in `/home/athar/Projects/Unsloth_Core`.

## Load Order for Agents

1. Read root `AGENTS.md` first; it is the source of truth.
2. Read this folder only when needing compact context recovery or memory discipline.
3. Use `memory_search` before adding memories.
4. Use `ctx_search(sort: "timeline")` after compaction/resume to recover prior session decisions.

## Key Files

- `PROJECT_PROFILE.md` — concise repo architecture and conventions.
- `COMMANDS.md` — safe common commands.
- `WORKFLOWS.md` — repeatable Unsloth_Core operating workflows.
- `MEMORY_POLICY.md` — how to decide what belongs in memory vs skill vs file.
- `CONTEXT_INDEX.md` — sources worth indexing/searching.

## Standing User Directive

Populate and maintain this local `.pi` workspace with only the structure and durable files needed for best performance in this project.
