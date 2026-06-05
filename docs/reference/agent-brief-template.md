---
name: <agent-name>
description: "<one-liner describing the agent's role>"
version: 1.0.0
last_verified: 2026-06-05
source_order:
  - 1. Live repo/tool output (always check reality before reading docs)
  - 2. AGENTS.md (entrypoint with hard rules)
  - 3. docs/INDEX.md → specific reference doc
  - 4. .hermes/skills/<relevant> or .codex/skills/<relevant>
  - 5. Other agent folders (stale unless re-verified)
---

# <Agent Name>

## Mission

<One paragraph describing what this agent does in the pipeline and when it's invoked.>

## Ownership

<What this agent owns — exact file globs, path patterns, or system endpoints.>

- `data/npcs/specs/<npc>.json`
- `src/core/training/train.py`

## First Commands

```bash
source unsloth_env/bin/activate
./ucore audit check
<agent-specific preflight or validation command>
```

## Workflow

<Numbered steps or decision tree describing the agent's standard procedure.>

1. Validate inputs with `<command>`.
2. Run `<pipeline-stage>`.
3. Verify output at `<path>`.
4. Report result.

## Never (hard rules)

<Non-negotiable boundaries. Do not lower thresholds, skip quality gates, or fabricate results.>

- Do not train production LoRA on template data.
- Do not skip quality gates.
- Do not lower eval thresholds to force a pass.

## Handoff

<Expected output format for this agent's results.>

```
Done: <summary>
Changed: <files>
Ran: <commands>
Result: <pass/fail + evidence>
Blocked: <blocker if any>
Next: <single recommended next action>
```

See also: `docs/project-state.md` for current NPC status, `docs/INDEX.md` for full doc navigation.
