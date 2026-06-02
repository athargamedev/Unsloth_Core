# LLMUnity Runtime Deploy

Use when deploying Unsloth_Core GGUF LoRA adapters into the Unity LLMUnity project.

## Runtime Target

- **Unity Project:** `~/Setup Guide In-Editor Tutorial/`
- **Model Folder:** `Assets/StreamingAssets/Models/`

## Deployment Rules

- **Base Model:** LLMUnity loads one shared llama3.2 3B base model.
- **Adapters:** Multiple lightweight LoRA adapter GGUFs are swapped at runtime.
- **Runtime Swap:** NPC switching involves swapping the system prompt AND activating the corresponding adapter.

## Deployment Steps

1. Export the GGUF adapter via `./ucore train ... --export-gguf`.
2. Locate the exported file at `artifacts/exports/<npc>/<npc>-lora-f16.gguf`.
3. Copy/Move the adapter to the Unity `StreamingAssets/Models/` directory.
4. Verify the `NPCLoraLoader` or equivalent component in Unity recognizes the new adapter.
