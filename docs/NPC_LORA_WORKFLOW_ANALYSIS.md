# NPC LoRA Workflow Analysis

This document summarizes the current NPC LoRA workflow in `Unsloth_Core`, the major gaps found during workflow review, and the backlog needed to make the pipeline reliable for Unity/LLMUnity NPC deployment backed by Supabase.

## Current Pipeline

The project already has a usable four-stage pipeline:

1. **Subject specification** in `subjects/{npc_key}.json` defines persona, teaching scope, dialogue rules, quest behavior, refusal boundaries, and research queries.
2. **Dataset generation** writes ChatML JSONL to `datasets/{npc_key}/{technique}/train.jsonl` and `datasets/{npc_key}/{technique}/validation.jsonl`.
3. **Unsloth LoRA training** produces run artifacts under `outputs/{npc_key}/runs/{run_id}` with `outputs/{npc_key}/latest` expected to point at the current run.
4. **Export and validation** produce GGUF or adapter artifacts under `exports/{npc_key}` and run smoke/evaluation checks before Unity handoff.

The canonical CLI is `./ucore` for common workflows:

```bash
./ucore generate subjects/chemistry_instructor.json --technique notebooklm
./ucore generate subjects/chemistry_instructor.json --technique ollama
./ucore sanitize datasets/chemistry_instructor/notebooklm/train.jsonl
./ucore train subjects/chemistry_instructor.json --preset smoke --from-spec
./ucore smoke exports/chemistry_instructor/model.gguf --spec subjects/chemistry_instructor.json
./ucore pipeline subjects/chemistry_instructor.json --preset smoke
```

Direct scripts remain useful when a workflow needs lower-level control: `scripts/generate_dataset.py`, `scripts/sanitize_dataset.py`, `scripts/train.py`, `scripts/export.py`, `scripts/export_adapter.py`, `scripts/smoke_test.py`, `scripts/evaluate.py`, and related evaluation helpers.

## Findings

### What is solid

- Subject specs, datasets, outputs, exports, and evaluation reports already have recognizable project conventions.
- NotebookLM, Ollama, and template dataset techniques are documented as separate generation modes.
- Training presets make smoke and low-VRAM iteration practical on consumer GPUs.
- Supabase tables exist for NPC profiles, dialogue sessions/turns, memories, embeddings, relation graphs, and test results.

### Known gaps

- `notebooklm` must be a real CLI/import workflow, not a silent template fallback.
- `ollama` should stay first-class for local/private iteration and synthetic expansion.
- Dataset technique lists and autodetection behavior need to be normalized across config, scripts, CLI, and docs.
- Some evaluation/export helpers disagree about whether the source of truth is `outputs/{npc_key}` or `outputs/{npc_key}/runs/{run_id}`.
- Smoke/eval tracking has known schema and CLI drift that should be fixed before promotion automation relies on it.
- Export and Unity handoff need checksum, prompt-format, promotion-status, and manifest validation.
- Supabase RLS is acceptable for local development only; shared/prod deployments need locked-down policies.
- Model-family differences should be handled through model profiles first, then wrappers/scripts only when behavior diverges.

## Canonical artifact map

| Artifact | Owner | Path |
| --- | --- | --- |
| Subject spec | Human/agent author | `subjects/{npc_key}.json` |
| Dataset | Generation workflow | `datasets/{npc_key}/{technique}/train.jsonl` and `validation.jsonl` |
| Sanitized dataset/report | Sanitizer | Same dataset tree or explicit sanitized output/report path |
| Training run | `scripts/train.py` / `./ucore train` | `outputs/{npc_key}/runs/{run_id}` |
| Current run pointer | Training workflow | `outputs/{npc_key}/latest` |
| TensorBoard logs | Training workflow | `outputs/{npc_key}/runs/{run_id}` or `outputs/{npc_key}/runs/` when configured |
| GGUF/export manifest | Export workflow | `exports/{npc_key}` |
| Evaluation reports | Evaluation workflow | `eval/reports/{npc_key}` and `eval/comparisons` |
| Runtime profile | Supabase/Unity sync | `npc_profiles` |

## Implementation backlog

### Blocking

- Add or repair explicit NotebookLM CLI/import support for `--technique notebooklm`.
- Verify local Ollama generation for `--technique ollama` and document the required local model.
- Fix smoke testing and tracking so default smoke runs produce actionable results.
- Align evaluation tracking with the current Supabase `test_results` schema.
- Make export scripts consistently resolve `outputs/{npc_key}/latest` and explicit run directories.
- Normalize dataset technique support across `_config/paths.py`, generation, evaluation, and `./ucore`.

### Important

- Add strict dataset validation for ChatML roles, max three-sentence assistant responses, duplicates, AI artifacts, and category balance.
- Produce machine-readable sanitize/eval reports.
- Rank candidates by a composite promotion score rather than training loss alone.
- Add checksums and promotion metadata to export/Unity manifests.
- Sync promoted artifacts into Supabase `npc_profiles`.

### Later

- Add model-family profiles under `configs/model_profiles/` before creating separate training scripts.
- Add runtime feedback/event tables or a clear contract for Unity-owned feedback capture.
- Harden Supabase RLS before any shared or production deployment.
- Add regression tests around CLI path conventions, dataset validation, export discovery, smoke parsing, and tracking inserts.

## Open decisions

- Which NotebookLM CLI/import executable and raw export format should be canonical on this machine?
- Which Ollama model should be the default generator for local datasets?
- Should Unity consume merged GGUF only, LoRA adapter GGUF only, or both?
- What Unity project path should deployment validation target?
- Which model families beyond Llama/Qwen are expected soon enough to justify model-specific wrappers?
