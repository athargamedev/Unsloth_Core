---
name: llmunity-runtime-deploy
description: "Codex deploy shim — canonical version lives at .hermes/skills/. This file adds Codex-specific deploy path notes on top of the Hermes master."
last_verified: 2026-06-05
version: 1.0.0
master: .hermes/skills/llmunity-runtime-deploy/SKILL.md
---

# LLMUnity Runtime Deploy (Codex shim)

**This skill is canonical at `.hermes/skills/llmunity-runtime-deploy/SKILL.md`.** Codex agents always load it from there for the full content (components, prompt contract, GladeKit, verification).

This file adds a Codex-specific deploy note:

## Deploy

```bash
cp artifacts/exports/<npc>/<npc>-lora-f16.gguf \
  "/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/"
```

Confirm actual export path first; older notes may refer to `exports/<npc>/unity/`.

## Report Format

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```
