# Configs

This directory is intentionally small. The current project focus is two simple Llama 3.2 3B NPCs (`history_guide`, `chef_assistant`) trained locally with W&B tracking and evaluated with remote/hosted services where useful.

## Required files

- `lora-sft-base.yaml` — canonical base training config used by `scripts/validate_config.py` and `scripts/plan_execution.py`.
- `presets/fast-3b.yaml` — standard production preset for Llama 3.2 3B on the RTX 3060 6GB workflow.
- `presets/safe-any.yaml` — OOM fallback preset.
- `presets/smoke.yaml` — tiny smoke-test preset.
- `presets/wandb.yaml` — convenience preset that enables W&B when no other preset is needed. For normal training, prefer `--preset fast-3b --wandb` because only one `--preset` is supported.
- `base_configs/unsloth-Llama-3.2-3B-Instruct-bnb-4bit.json` — cached clean base model config used by GGUF LoRA export when Hugging Face config lookup is unavailable.
- `eval-presets.yaml` — standard evaluation profiles.
- `promotion-rules.yaml` — minimum quality gates checked after training.
- `workload-policy.yaml` — local-vs-remote planning heuristics.

## Removed on purpose

Older Qwen, 0.5B/1B, and duplicate full LoRA config files were removed to avoid preset drift. Re-add a model-specific preset only when the project actively trains that model family again.
