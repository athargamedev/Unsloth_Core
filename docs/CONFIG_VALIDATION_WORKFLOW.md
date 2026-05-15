# Config Validation Workflow

This workflow validates the effective training configuration before running expensive training jobs.

## Why this exists

Phase 2 normalizes config behavior around one hierarchy:

base config -> preset overrides -> CLI overrides

Validation catches common drift:
- wrong preset names
- non-canonical dataset paths
- output dirs outside `outputs/`
- model IDs that do not follow expected Unsloth `-bnb-4bit` convention
- mismatch between NPC key and dataset folder

## Command (recommended)

Use unified CLI:

```bash
./ucore validate-config --spec subjects/chemistry_instructor.json --preset fast-3b --data subjects/datasets/chemistry_instructor/onyx/train.jsonl --format yaml
```

Strict mode (warnings fail the command):

```bash
./ucore validate-config --spec subjects/chemistry_instructor.json --preset llama-3b-fast --data subjects/datasets/chemistry_instructor/onyx/train.jsonl --require-canonical --strict
```

## Direct script usage

```bash
python scripts/validate_config.py --spec subjects/chemistry_instructor.json --preset fast-3b
python scripts/validate_config.py --config configs/lora-sft-base.yaml --preset quality-1.7b --npc-key chemistry_instructor --data subjects/datasets/chemistry_instructor/onyx/train.jsonl
```

Output formats:
- `--format yaml` (default)
- `--format json`

## Canonical path expectations

Dataset train path should be:

`subjects/datasets/{npc_key}/{technique}/train.jsonl`

Where `technique` is one of:
- onyx
- ollama
- template

Training outputs are expected under:

`outputs/{npc_key}/...`

## Integration recommendation

Before starting any new run:
1) run `validate-config`
2) fix warnings if possible
3) run with `--strict` for production runs
4) only then launch `train`/`pipeline`

## Notes

- Validator is non-destructive.
- It resolves and prints the effective config exactly as training would consume it.
- It supports both `--spec` and direct `--config` modes.
- For legacy flat datasets, run `./ucore migrate-datasets` first.
