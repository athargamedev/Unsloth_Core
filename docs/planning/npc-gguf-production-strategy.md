# NPC GGUF Production Strategy

Goal: build one repeatable production system for Unity-loadable NPC LoRA GGUF adapters, not endless per-NPC weak-concept patching.

Status: strategy baseline for Unsloth_Core. Use this to guide next implementation work before more Marvel repair cycles.

## North star

Each NPC should move through the same evidence-backed pipeline:

1. Spec contract
2. Grounded source/reference doc
3. Dataset blueprint
4. Dataset generation preset
5. Sanitizer + structural gate
6. DeepEval/Confident release gate
7. Training preset
8. GGUF adapter export
9. Base+LoRA runtime eval
10. Unity deployment readiness check

NPC-specific tweaks are allowed, but only inside bounded fields:

- subject concepts
- voice/tone tokens
- refusal boundaries
- example density targets
- validation prompts

Do not invent a new workflow per NPC.

## Production invariant

A production adapter must satisfy all of these:

- Dataset is grounded, not template-only.
- Dataset hash in `quality_summary.json` matches current `train_clean.jsonl`.
- DeepEval release gate passes for the exact dataset hash.
- Confident AI run exists for the release gate.
- W&B run exists for gate/train/eval when cloud judging/tracking is used.
- Training loss passes promotion rules or is explicitly marked non-promoted.
- Exported GGUF is adapter mode for LLMUnity unless full-merge is intentionally requested.
- Final eval compares base-only vs base+LoRA with the same base GGUF.
- Final eval produces timestamped `.md` and `.html` reports.
- Candidate beats or meaningfully improves over baseline; otherwise artifact is smoke/provisional.

## Canonical artifact chain

Every stage should carry these IDs forward:

- `npc_key`
- `technique`
- `base_model`
- `dataset_hash`
- `quality_gate_id`
- `confident_url`
- `wandb_run_id`
- `train_run_id`
- `export_hash`
- `eval_report_id`

Minimum artifact locations:

- Spec: `data/npcs/specs/<npc>.json`
- Primer/reference: `data/npcs/reference_docs/<npc>_primer.md`
- Raw dataset: `data/datasets/<npc>/<technique>/train.jsonl`
- Clean dataset: `data/datasets/<npc>/<technique>/train_clean.jsonl`
- Quality summary: `data/datasets/<npc>/<technique>/quality_summary.json`
- Quality failures: `data/datasets/<npc>/<technique>/quality_failures.json`
- Training run: `artifacts/models/<npc>/runs/<run_id>/`
- Export: `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- Eval report: `artifacts/eval/reports/<npc>/eval_<timestamp>.{md,html}`

If legacy `subjects/...` mirrors are still read by code, sync them, but treat `data/...` as the operator-facing target unless live path helpers say otherwise.

## Dataset blueprint preset

Default production dataset structure:

| Category | Purpose | Min rows | Target rows | Shape |
|---|---:|---:|---:|---|
| identity | who/voice/role contract | 8 | 12-16 | short, concrete self-definition |
| teaching | domain explanations | 32 | 80-120 | 2-3 sentences, one concrete example |
| dialogue | multi-turn continuity | 16 | 32-48 | conversational, remembers previous turn |
| quest | scenario/task guidance | 8 | 16-24 | action-oriented next step |
| refusal | safe/out-of-scope redirect | 8 | 16-24 | boundary + in-scope alternative |

Density rule for Unity NPC usefulness:

- Identity/refusal: 20-40 words
- Teaching/dialogue/quest: 35-55 words
- 2-3 sentences unless NPC spec is stricter
- one concrete subject example when teaching
- one tactical/runtime implication when useful

This prevents the Marvel failure pattern: gate-passing rows that train a terse adapter which loses to base model verbosity.

## Generation preset strategy

Use named presets instead of one-off row edits:

### `npc-production-grounded`

Use for production data.

- technique: grounded approved workflow / ollama only when grounded by primer
- source: primer headings + explicit concept map
- template data: forbidden except smoke/dev
- categories: all five required
- min target: 120+ rows when subject complexity is medium/high
- output: ChatML with complete metadata
- validation split: retained

### `npc-smoke-template`

Use only for CLI, sanitizer, train/export smoke.

- technique: template
- rows: minimum contract only
- never train production LoRA from this
- never mark production-ready

### `npc-density-repair`

Use when release gate passes but base+LoRA eval loses from terse answers.

- add rows only for weak concepts
- 35-55 word target
- concrete example + implication
- rerun release gate before retraining
- do not keep looping forever: max two repair cycles before changing training preset/rubric

## DeepEval / Confident strategy

Use three gates:

### 1. Structural gate

Run after sanitize.

Checks:

- rows kept/dropped
- category distribution
- metadata completeness
- dataset hash
- no unknown rows

### 2. Fast local gate

Purpose: cheap diagnostics.

- mode: fast
- cases/category: 1-2
- judge: local `qwen2.5:7b` unless freshly benchmarked otherwise
- result: repair hints only, not production approval

### 3. Release cloud gate

Purpose: train/no-train decision.

Required for production:

```bash
DEEPEVAL_DISABLE_CACHE=1 ./ucore dataset-eval data/npcs/specs/<npc>.json \
  --technique <technique> \
  --mode release \
  --cases-per-category 3 \
  --judge-provider wandb \
  --judge-model meta-llama/Llama-3.1-70B-Instruct \
  --identifier dataset-quality-<npc>-release-$(date +%s) \
  --display failing \
  --ignore-errors \
  --soft-fail \
  --confident \
  --wandb
```

Decision rule:

- 100% pass: train allowed.
- 90-99% pass: patch exact failing row/concept from Confident reason, rerun release gate.
- <90% pass: treat as preset/blueprint failure, not row patching.
- repeated same-class failures after two patches: improve preset/rubric/generator, not more manual examples.

## Training preset strategy

Default local 6GB preset for llama3.2 3B adapter:

- preset: `fast-3b` plus low-VRAM overrides if needed
- seq length: 512 for local safety
- batch: 1
- grad accumulation: 8
- LoRA: r16/alpha32 for quality attempt; r8/alpha16 only for OOM/smoke fallback
- packing: false
- W&B: enabled

Promotion is not just training loss.

Promotion needs:

- quality gate passed for exact dataset
- training loss passes configured rule or is accepted with documented exception
- final base+LoRA eval improves baseline
- no runtime load/export issues

## Runtime eval strategy

Always evaluate adapter as LoRA-on-base:

```bash
./ucore evaluate \
  --baseline .models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --candidate artifacts/exports/<npc>/<npc>-lora-f16.gguf \
  --base-model .models/llama-3.2-3b-instruct-q4_k_m.gguf \
  --spec data/npcs/specs/<npc>.json \
  --report-html \
  --wandb
```

Do not evaluate adapter GGUF standalone.

Final decision bands:

- candidate wins >=70%: production-ready candidate
- candidate wins 50-69%: likely usable, inspect weak concepts manually
- candidate wins 30-49%: provisional, repair density/rubric/training
- candidate wins <30%: not ready; revisit dataset blueprint or preset

Also inspect:

- candidate average words vs baseline
- refusal quality
- identity consistency
- category-level wins/losses
- Unity-style short prompt behavior

## Anti-loop rule

Do not spend unlimited time fixing per-NPC weak concepts.

Per NPC maximum before strategy review:

1. Initial production dataset gate
2. One exact Confident failure repair cycle
3. One density repair cycle if final eval shows terse adapter
4. One controlled training preset variant

If still not ready, stop and classify root cause:

- dataset blueprint weak
- generation model weak
- eval rubric biased
- training preset wrong
- base model too strong for adapter delta
- subject too broad for current row budget

Then improve the shared pipeline, not just that NPC.

## Implementation gaps to close next

1. Add named dataset generation presets for production/smoke/density-repair.
2. Add a canonical `npc-workflow.yaml` or manifest that binds dataset/eval/train/export presets.
3. Make `./ucore` print the full artifact chain and hashes at each stage.
4. Make dashboard show stage readiness from real artifacts, not assumptions.
5. Add DeepEval/Confident gate profiles so release command does not need long manual flags.
6. Add density metrics to final eval: avg words, sentence count, concrete-example presence.
7. Add anti-loop policy to feedback loop: after two same-class repairs, escalate to preset/blueprint issue.

## Current Marvel decision

Marvel is useful as a worked example, but do not keep treating every weak concept as the main work.

Current status from latest run:

- dataset release gate passed
- adapter improved from 0% to 29% candidate win rate
- adapter still not production-ready
- likely failure class: answer density + broad subject coverage

Next Marvel work should be one bounded density repair cycle only. After that, move to shared preset/manifest implementation.
