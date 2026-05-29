# Local Pi Workspace for Unsloth_Core

This folder is a project-local agent workspace. It stores lightweight project memory, reusable workflow notes, and context pointers that help Pi work safely in this repository.

## Layout

- `agent/projects-memory/Unsloth_Core/` — durable project profile, workflows, memory rules, and context index.
- `agent/projects-memory/Unsloth_Core/skills/` — project-local skill notes or wrappers.
- `agent/projects-memory/Unsloth_Core/notes/` — concise durable notes only; no raw logs or temporary TODOs.
- `agent/skills/` — optional project-local skills discoverable by humans/agents.
- `agent/pi-hermes-memory/` — notes about how to use memory tooling in this project.
- `context-mode/indexes/` — reserved for project-local context-mode references if needed.

## Rules

- Do not store secrets, API keys, private tokens, or raw datasets here.
- Do not store temporary task state; use this only for stable reusable context.
- Prefer `memory` / `memory_search` for durable searchable facts and `skill` for reusable procedures.
- Keep files concise so future agents can load them without wasting context.
