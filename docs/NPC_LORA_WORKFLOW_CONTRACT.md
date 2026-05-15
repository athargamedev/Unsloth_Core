# NPC LoRA Workflow Contract

This contract defines the expected paths, metadata, dataset techniques, testing gates, promotion rules, Unity handoff, Supabase expectations, and self-improvement loop for NPC LoRA/GGUF workflows in `Unsloth_Core`.

## Artifact paths

| Stage | Required path |
| --- | --- |
| Project root | `/home/athar/Projects/Unsloth_Core` |
| CLI | `./ucore` |
| Subject specs | `subjects/{npc_key}.json` |
| Datasets | `datasets/{npc_key}/{technique}/train.jsonl` and `validation.jsonl` |
| Training runs | `outputs/{npc_key}/runs/{run_id}` |
| Current run pointer | `outputs/{npc_key}/latest` |
| TensorBoard logs | `outputs/{npc_key}/runs/{run_id}` |
| Exports | `exports/{npc_key}` |
| Evaluation reports | `eval/reports/{npc_key}` and `eval/comparisons` |

Legacy paths such as `/home/athar/Projects/LLM_Training` and `~/.unsloth/studio` are migration references only. New workflow content must use the paths above.

## Required metadata fields

Promotion and handoff records should include:

- `npc_key`
- `run_id`
- `dataset_hash`
- `dataset_technique`
- `generation_method`
- `base_model`
- `model_family`
- `training_script_or_profile`
- `preset`
- `lora_rank`
- `lora_alpha`
- `quantization`
- `gguf_sha256`
- `eval_score`
- `judge_win_rate`
- `latency_ms`
- `tokens_per_second`
- `promotion_status`
- `promoted_at`
- `rollback_target`

## Dataset technique contracts

### `onyx`

Onyx is the production default, retrieval-grounded technique. It queries the local Onyx index for relevant document chunks and generates ChatML JSONL with full provenance metadata (source titles, document IDs, retrieval scores).

Expected command shape:

```bash
./ucore generate subjects/{npc_key}.json --technique onyx
```

The workflow must record the Onyx query, retrieved chunks, and final dataset hash. It must fail with a clear setup/connection error if Onyx is unavailable; it must not silently fall back to template data.

### `ollama`

Ollama is the local synthetic generation technique for private, offline, and rapid iteration.

Expected command shape:

```bash
./ucore generate subjects/{npc_key}.json --technique ollama
```

The workflow must record the local model name, prompt template, temperature/options, retries, generated category counts, and dataset hash. It should verify that Ollama is reachable and that outputs are valid ChatML before training.

### `template`

Template generation is allowed for scaffolding and smoke tests only. It should be marked as low-fidelity data in metadata and should not be promoted as a production dataset without an explicit waiver.

### Optional hosted techniques

`openai` and `anthropic` may be supported when configured. They must use the same artifact paths and metadata contract as the first-class techniques, including provider/model, prompt version, cost-sensitive settings, and generated dataset hash.

## Training profile/script decision rule

Use `scripts/train.py` and model profiles when differences are configuration-only: base model ID, max sequence length, batch size, gradient accumulation, LoRA rank/alpha, quantization, and export mode.

Introduce model-specific wrappers or scripts only when behavior differs: tokenizer/template handling, packing strategy, chat template, target modules, loss masking, Unsloth loading path, export procedure, or evaluation prompt format.

Canonical training commands:

```bash
./ucore train subjects/{npc_key}.json --preset smoke --from-spec
python scripts/train.py subjects/{npc_key}.json --from-spec --preset fast-3b
```

## Testing gates

| Gate | Purpose | Required result |
| --- | --- | --- |
| Gate 0: Static preflight | Validate spec, dataset shape, technique setup, and config compatibility | No blocking validation errors |
| Gate 1: Smoke pipeline | Run minimal generation/training/inference | No crashes, disclaimers, identity loss, or length violations |
| Gate 2: Candidate training | Train selected preset/profile | Run manifest, metrics, dataset hash, and config captured |
| Gate 3: Dialogue evaluation | Compare candidate against baseline | Composite score improves without critical regressions |
| Gate 4: Unity readiness | Validate GGUF, checksum, manifest, prompt format, and load assumptions | Handoff artifact is complete |
| Gate 5: Supabase runtime loop | Validate profile sync, dialogue/memory/eval tracking, and RLS posture | Runtime contract is satisfied or waived |

A candidate may be promoted only after all gates pass or a waiver is recorded with owner, reason, and rollback target.

## Unity handoff

Unity/LLMUnity handoff artifacts live under `exports/{npc_key}`. A promoted handoff should include the GGUF or adapter artifact, manifest, checksum, prompt format notes, quantization, model family, expected context length, and rollback target. The manifest should be suitable for syncing into Unity and Supabase `npc_profiles`.

## Supabase runtime and security expectations

Local Supabase owns or mirrors runtime state for `npc_profiles`, dialogue sessions/turns, memories, embeddings, relation graphs, and `test_results`. Unity may own runtime writes, but this repo must define the promotion/eval metadata it expects to read or write.

Permissive public RLS is acceptable only for local development. Shared or production environments must protect player dialogue, memory, embeddings, eval results, and NPC prompt/profile editing from unauthenticated writes.

## Self-improvement loop

1. Capture failures from smoke tests, eval reports, human notes, and Unity runtime dialogue.
2. Classify each failure as persona, factual, refusal, memory, latency, formatting, hallucination, unsafe, or integration-related.
3. Store structured evidence locally and, when configured, in Supabase.
4. Convert validated failures into dataset patches or validation prompts.
5. Use Onyx for retrieval-grounded patches, Ollama for local synthetic patches, and manual curation for critical examples.
6. Sanitize patched data and keep validation examples separate from training examples.
7. Train smoke first, then fast/quality only after smoke passes.
8. Evaluate against the promoted baseline and promote only if composite quality improves without critical regressions.
9. Export, checksum, sync metadata, deploy to Unity, monitor runtime behavior, and repeat.
