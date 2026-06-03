---
name: llmunity-runtime-deploy
description: Use when deploying Unsloth_Core GGUF LoRA adapters into the Unity LLMUnity project, checking base+LoRA runtime behavior, prompt contracts, Unity StreamingAssets paths, or Unity-side adapter switching.
---

# LLMUnity Runtime Deploy

Runtime target: `/home/athar/Setup Guide In-Editor Tutorial/`

Unity model folder: `Assets/StreamingAssets/Models/`

LLMUnity should load one shared llama3.2 3B base GGUF and swap lightweight LoRA adapter GGUFs plus NPC system prompts.

## Deploy

```bash
cp artifacts/exports/<npc>/<npc>-lora-f16.gguf \
  "/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/"
```

Confirm actual export path first; older notes may refer to `exports/<npc>/unity/`.

## Runtime Checks

- Base model remains loaded once.
- Per-NPC swap activates adapter and prompt, not a full base reload.
- LLMUnity server process includes expected `--lora` flag(s).
- Adapter GGUF is non-empty and matches the training/eval base model.
- Prompt stays compact and uses identity, voice, knowledge, and rules sections.

## GladeKit/Unity

GladeKit MCP requires Unity Editor running. Connection errors usually mean Unity or the bridge is unavailable.

```bash
DISPLAY=:1 ~/Unity/Hub/Editor/6000.4.5f1/Editor/Unity \
  -projectPath "/home/athar/Setup Guide In-Editor Tutorial"
```

## Report Format

Use:

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```

