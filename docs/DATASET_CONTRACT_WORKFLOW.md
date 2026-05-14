# Dataset Contract Workflow (Phase 3)

> **Cross-reference**: For the complete dataset structure, generation logic, sanitization rules, training data flow, and minimum requirements, see [`docs/DATASET_STRUCTURE_AND_LOGIC.md`](DATASET_STRUCTURE_AND_LOGIC.md).

This phase enforces a single dataset path contract across generation, sanitization, training, and evaluation.

Contract
- Train file: `datasets/{npc_key}/{technique}/train.jsonl`
- Validation file: `datasets/{npc_key}/{technique}/validation.jsonl`

Valid techniques
- `notebooklm` (production default)
- `ollama`
- `openai`
- `anthropic`
- `template`

## New tools

1) Validate canonical dataset path strictly

```bash
./ucore validate-config \
  --spec subjects/chemistry_instructor.json \
  --preset llama-3b-fast \
  --data datasets/chemistry_instructor/notebooklm/train.jsonl \
  --require-canonical \
  --strict
```

2) Enforce canonical input during sanitize

```bash
./ucore sanitize datasets/chemistry_instructor/notebooklm/train.jsonl --strict-canonical
```

3) Migrate legacy flat datasets to canonical structure

Dry-run:

```bash
./ucore migrate-datasets
```

Apply as copy (safe):

```bash
./ucore migrate-datasets --apply
```

Apply as move (destructive):

```bash
./ucore migrate-datasets --apply --move
```

## Implementation notes

- `paths.infer_validation_path()` now standardizes validation lookup.
- Train pipeline uses this shared helper instead of ad-hoc suffix logic.
- Pipeline sanitize step now uses `--strict-canonical`.

## Recommended run order

1) `./ucore migrate-datasets` (dry-run if legacy files exist)
2) `./ucore validate-config ... --require-canonical --strict`
3) `./ucore pipeline ...` or `./ucore train ...`

This keeps dataset structure predictable and reduces hidden path bugs.
