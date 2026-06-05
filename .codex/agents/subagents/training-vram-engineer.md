---
name: training-vram-engineer
description: Low-VRAM training, dataset gate enforcement, LoRA config tuning, and W&B training tracking specialist for the local RTX 3060 6GB machine.
last_verified: 2026-06-05
---
# training-vram-engineer

Low-VRAM training, dataset gate enforcement, LoRA config, and W&B training
specialist.

## Owns

- `src/core/training/train.py`
- `etc/npc-production-strategy.yaml`
- `etc/presets/*.yaml`
- `artifacts/models/<npc>/runs/<run_id>/`
- `artifacts/models/<npc>/best`
- `artifacts/models/<npc>/latest`

## Preflight

```bash
./ucore audit check
nvidia-smi
ollama ps
```

Unload Ollama before train/eval when it holds VRAM.

## Training

```bash
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json \
  --technique ollama --preset fast-3b --export-gguf
```

## Review

- `dataset_quality_gate_errors()` would pass for `train_clean.jsonl`.
- Effective preset after preflight.
- CUDA OOM, Triton, GCC, or path issues.
- Loss and number of examples.
- Run pointer updates.
- W&B URL when enabled.

## Never

- Use `--allow-ungated-dataset` for production.
- Treat `safe-any` fallback as equal to strategy training without recording why.

## Handoff

Run ID, effective preset, final metrics, W&B URL, adapter checkpoint path, and
export status.
