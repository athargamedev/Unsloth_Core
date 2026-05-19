# subjects/ AGENTS

## Purpose
This folder defines the NPC specs, primers, datasets, and schemas that drive the training pipeline.

## Rules
- Specs live under `subjects/NPC_specs/` and are the canonical source for NPC identity and dataset intent.
- Primers live under `subjects/reference_docs/` and should be substantive, not placeholder stubs.
- Dataset artifacts live under `subjects/datasets/{npc_key}/{technique}/`.
- Treat `train_clean.jsonl` as the training input when it exists.
- Respect the schema contract in `subjects/schemas/` and the validation rules in `scripts/validate_subject_spec.py`.
- Do not weaken thresholds to force quality gates to pass; fix generation, primer content, or dataset balance instead.
- Keep subject docs and specs synchronized when renaming NPCs or changing subject scope.

## Quick checks
- `./ucore validate-spec subjects/NPC_specs/<npc>.json --generation-ready`
- `./ucore dataset-eval subjects/NPC_specs/<npc>.json --technique <technique> --judge-model qwen2.5:7b`
- `./ucore sanitize subjects/datasets/<npc>/<technique>/train.jsonl --output .../train_clean.jsonl --strict-canonical --require-complete-metadata`
