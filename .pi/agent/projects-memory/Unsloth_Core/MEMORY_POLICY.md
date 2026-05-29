# Memory Policy for Unsloth_Core

Use this together with the `compact-memory-extraction` skill.

## Store in Memory

- Stable user preferences and corrections.
- Durable project conventions not already obvious from files.
- Environment facts likely to matter again.
- Tool quirks and failed approaches with clear reasons.

## Store as Skills

- Multi-step procedures that should be reused.
- Debugging playbooks.
- Project-specific workflows that need ordered steps and verification.

## Store in `.pi` Files

- Compact reference material useful to future agents.
- Pointers to canonical repo files.
- Human-readable project-local context not requiring search.

## Do Not Store

- Secrets, API keys, tokens, hashes, credentials.
- Raw logs, raw generated datasets, model outputs, or large artifacts.
- Temporary task progress, TODOs, one-off observations.
- Duplicates of existing AGENTS.md content unless summarized as a quick index.

## Workflow

1. Search: `memory_search` with concrete terms and project filter where possible.
2. Decide target: `user`, `project`, `memory`, or `failure`.
3. Add or replace with one concise entry.
4. Verify by searching again if the memory is important.
