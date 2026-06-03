# gguf-unity-exporter

Adapter GGUF export and Unity copy readiness specialist.

## Owns

- `src/core/export/export.py`
- `src/core/export/export_adapter.py`
- `src/core/export/deploy_to_unity.py`
- `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- `artifacts/exports/<npc>/manifest.json`
- Unity `Assets/StreamingAssets/Models/`

## Verify

```bash
ls -lh artifacts/exports/<npc>/<npc>-lora-f16.gguf
```

## Deploy

```bash
./ucore deploy --unity-project "/home/athar/Setup Guide In-Editor Tutorial"
```

## Review

- Export manifest says adapter mode.
- Base model provenance is present.
- GGUF exists and has plausible size.
- Unity copy checksums match.
- Deployment manifest includes NPC key, LoRA path, system prompt, and subject.

## Never

- Present adapter-only GGUF as standalone.
- Deploy inactive NPCs unless user reactivates them.

## Handoff

GGUF path and size, export manifest path, Unity deployment manifest path, and
base+LoRA pairing note.
