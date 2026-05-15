# Subject Spec Review Workflow

Use this checklist before generating data or starting training from any `subjects/*.json` file.

## 1. Static subject-spec review

Validate the spec structure first:

```bash
./ucore validate-spec subjects/chemistry_instructor.json
./ucore validate-spec --all
```

`--all` is a repository-wide audit of every checked-in `subjects/*.json` file. It will fail when draft,
experimental, or incomplete specs are present, so treat it as a whole-repo hygiene check rather than a green
production gate unless every spec in `subjects/` is intended to be trainable.

Use `--strict` when a review gate should fail on warnings, not only errors:

```bash
./ucore validate-spec subjects/workflow_assistant.json --strict
```

The validator checks JSON parsing, required generation/training fields, `npc_key` naming, filename alignment, identity/teaching/dialogue/refusal shape, research queries, prompt coherence, and dataset category counts.

## 2. Training config review

Resolve the effective training configuration without launching training:

```bash
./ucore validate-config --spec subjects/chemistry_instructor.json --preset smoke --strict
```

This catches preset, model, output, and canonical dataset-path issues separately from subject-spec issues.

## 3. Execution placement

Plan whether the run belongs on the local machine or remote Colab before expensive work:

```bash
./ucore plan-execution --spec subjects/chemistry_instructor.json --preset fast-3b
```

## 4. Dataset and training gates

After generation, sanitize the produced JSONL before training:

```bash
./ucore sanitize subjects/datasets/chemistry_instructor/onyx/train.jsonl --strict-canonical
```

Use smoke presets for early pipeline checks and reserve full presets for specs that pass review.

## 5. Smoke and evaluation gates

After export, run a smoke test and then deeper evaluation when promoting a candidate:

```bash
./ucore smoke exports/chemistry_instructor/<model>.gguf --spec subjects/chemistry_instructor.json
./ucore evaluate --candidate exports/chemistry_instructor/<model>.gguf --spec subjects/chemistry_instructor.json --track
```

Treat validation errors as blockers. Treat warnings as review items; use `--strict` for production-ready specs.
