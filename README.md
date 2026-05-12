# Unsloth_Core

A clean, reproducible pipeline for building NPC dialogue models with Unsloth, exporting GGUF for Unity, and tracking evaluation results (optionally in Supabase).

## What this project does
- Generate training datasets from NPC subject specs
- Sanitize and validate datasets
- Train LoRA adapters with preset-driven settings
- Export deployable GGUF artifacts
- Run smoke tests and evaluations
- Compare runs and track quality over time
- Deploy to Unity StreamingAssets

## Canonical project structure

- `subjects/{npc_key}.json`
- `datasets/{npc_key}/{technique}/train.jsonl`
- `datasets/{npc_key}/{technique}/validation.jsonl`
- `outputs/{npc_key}/runs/{run_id}/...` (adapters/checkpoints/metrics)
- `exports/{npc_key}/{npc_key}-{model_short}-{quant}.gguf`
- `eval/reports/{npc_key}/...`
- `eval/comparisons/...`
- `supabase/migrations/...`

Techniques:
- `notebooklm` (production default)
- `ollama` (local alt)
- `template` (smoke/fallback only)

## Quick start

1) Activate environment
```bash
source unsloth_env/bin/activate
```

2) Full pipeline (generate -> sanitize -> train -> export)
```bash
./ucore pipeline subjects/chemistry_instructor.json --preset fast-3b
```

3) Smoke test exported model
```bash
./ucore smoke exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-q4_k_m.gguf --spec subjects/chemistry_instructor.json
```

## Unified CLI (recommended)

Use `./ucore` as the main entrypoint:

```bash
./ucore generate subjects/chemistry_instructor.json --technique notebooklm
./ucore sanitize datasets/chemistry_instructor/notebooklm/train.jsonl --strict-canonical
./ucore train subjects/chemistry_instructor.json --from-spec --preset fast-3b
./ucore smoke exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-q4_k_m.gguf --spec subjects/chemistry_instructor.json
./ucore dashboard --port 8000
./ucore validate-config --spec subjects/chemistry_instructor.json --preset llama-3b-fast --data datasets/chemistry_instructor/notebooklm/train.jsonl --require-canonical --strict
./ucore migrate-datasets
```

## Direct scripts (advanced)

```bash
python scripts/generate_dataset.py subjects/chemistry_instructor.json --technique notebooklm
python scripts/sanitize_dataset.py datasets/chemistry_instructor/notebooklm/train.jsonl
python scripts/train.py subjects/chemistry_instructor.json --from-spec --preset fast-3b
python scripts/export.py chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit --quantization q4_k_m
python scripts/evaluate.py --candidate exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-q4_k_m.gguf --spec subjects/chemistry_instructor.json
```

## Training presets

Preset files live in:
- `configs/presets/*.yaml`

Base config:
- `configs/lora-sft-base.yaml`

Common presets:
- `smoke`
- `llama-1b-fast` (recommended for quick iteration)
- `llama-3b-fast` (recommended default)
- `llama-3b-quality` (recommended for higher quality)
- `fast-1.7b`
- `fast-3b`
- `quality-1.7b`
- `safe-any`

Note: legacy Qwen-oriented presets remain for backward compatibility, but the Unity dialogue workflow is Llama-first.

## Naming conventions

- `npc_key`: snake_case (from `subjects/*.json`)
- `run_id`: `YYYYMMDD_{preset}_{seq}`
- GGUF filename:
  - `{npc_key}-{model_short}-{quant}.gguf`
  - example: `chemistry_instructor-llama3.2-3b-q4_k_m.gguf`

## Unity deployment

Use exported GGUF artifacts from `exports/{npc_key}/`.

Project convention:
- Deployable model files belong in Unity at:
  - `Assets/StreamingAssets/Models/`

You can use:
```bash
python scripts/deploy_to_unity.py
```

## Supabase integration

Local Supabase (project-specific defaults):
- DB: `localhost:15434`
- API/Kong: `localhost:16437`
- Studio: `localhost:16438`

Schema and migrations:
- `supabase/migrations/`

Useful flow:
```bash
supabase start
```

## Evaluation and comparison

Outputs:
- `eval/reports/{npc_key}/`
- `eval/comparisons/`
- `eval/results/eval_results.jsonl`

Use:
```bash
python scripts/smoke_test.py exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-q4_k_m.gguf --spec subjects/chemistry_instructor.json
python scripts/compare_runs.py outputs/chemistry_instructor/runs/*
```

## Troubleshooting

- CUDA OOM:
  - use `--preset safe-any`
- Wrong model format:
  - use Unsloth `-bnb-4bit` models
- Loss not improving:
  - reduce LR (e.g. `1e-4`), verify data quality and response-only training
- Confusing output locations:
  - training intermediates in `outputs/`, deployables in `exports/`

## Key docs

- `docs/NOTEBOOKLM_WORKFLOW.md`
- `docs/OLLAMA_WORKFLOW.md`
- `docs/TRAINING_WORKFLOW.md`
- `docs/CONFIG_VALIDATION_WORKFLOW.md`
- `docs/LLAMA_UNITY_PROFILE.md`
- `docs/DATASET_CONTRACT_WORKFLOW.md`
- `docs/EXPORT_WORKFLOW.md`
- `docs/EVALUATION_WORKFLOW.md`
- `docs/PROJECT_REFACTOR_PLAN_FOR_UNITY_SUPABASE.md`
