---
name: unsloth-core-low-vram-training
description: "Codex low-VRAM shim — canonical version lives at .hermes/skills/. This file adds Codex-specific context precedence on top of the Hermes master."
last_verified: 2026-06-05
version: 1.0.0
master: .hermes/skills/unsloth-core-low-vram-training/SKILL.md
---

# Unsloth_Core Low-VRAM Training (Codex shim)

**This skill is canonical at `.hermes/skills/unsloth-core-low-vram-training/SKILL.md`.** Codex agents always load it from there for the full content (defaults, command patterns, failures).

This file adds Codex-specific context precedence:

## Codex Context Order

Read `.codex/references/project-context.md` and `.codex/references/current-commands.md` before expensive train/eval work.

If `.hermes`, `.agents`, or older docs conflict, verify current repo/tool output and follow the newer verified source.

## Done Evidence

Report concrete artifact paths: run dir, GGUF path, eval report, feedback JSON, and GPU/model checks used.
