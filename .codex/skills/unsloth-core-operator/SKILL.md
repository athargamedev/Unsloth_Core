---
name: unsloth-core-operator
description: "Codex-operator shim — canonical version lives at .hermes/skills/. This file adds Codex-specific source order on top of the Hermes master."
last_verified: 2026-06-05
version: 1.0.0
master: .hermes/skills/unsloth-core-operator/SKILL.md
---

# Unsloth_Core Operator (Codex shim)

**This skill is canonical at `.hermes/skills/unsloth-core-operator/SKILL.md`.** Codex agents always load it from there for the full content (commands, paths, repair rules, anti-loop).

This file adds Codex-specific context precedence:

## Source Order

Use `AGENTS.md` first. Then read `.codex/references/project-context.md` and `.codex/references/current-commands.md` when commands or paths matter.

If `.hermes`, `.agents`, or older docs conflict with `AGENTS.md`, verify current repo/tool output and follow the newer verified source.

## Report Format

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```
