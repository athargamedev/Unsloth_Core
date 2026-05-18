# NPC Data Generation Contract

This is the minimum contract for generating new NPC datasets. It defines the
source inputs, reference-doc pattern, SFT dataset requirements, and RL dataset
shape. Use it before any training run.

## 1. Source of Truth

Fresh datasets must be generated from:

- `subjects/{npc_key}.json` for identity, system prompt, categories, counts, and behavior rules.
- `subjects/reference_docs/{npc_key_or_subject}_primer.md` for grounded domain facts.
- `subjects/schemas/*.schema.json` for machine-readable record formats.

Do not generate new training data from old `subjects/datasets/**/train*.jsonl`
files. Those files are generated artifacts, not source material.

## 2. Reference Doc Pattern

Each `reference_doc` must be a Markdown file under `subjects/reference_docs/`.
Minimum requirements:

- One H1 title naming the NPC or subject.
- At least 5 H2 sections.
- At least 20 concrete bullet facts or examples.
- At least 250 words.
- No placeholder language such as `TODO`, `TBD`, `FIXME`, `stub`, or `placeholder`.
- Include safety, refusal, boundary, misconception, or myth notes so refusal and correction data can be generated.

Recommended section pattern:

- `## Scope and NPC Use`: what the NPC should teach and what it should not claim.
- `## Core Concepts`: high-value concepts that should appear in teaching examples.
- `## Domain Facts`: concise grounded facts with dates, numbers, definitions, or procedures.
- `## Worked Examples or Scenarios`: concrete learner questions, mistakes, or tasks.
- `## Common Misconceptions`: myths or likely wrong assumptions to correct.
- `## Safety Boundaries`: refusal boundaries and safe redirects for this domain.
- `## Vocabulary`: domain terms the model should use consistently.

Reference docs should be factual, compact, and easy to sample. Prefer bullets
over long prose. Include exact terms that should appear in dataset `concept`
metadata.

## 3. SFT Dataset Requirements

Canonical path:

```text
subjects/datasets/{npc_key}/{technique}/train.jsonl
subjects/datasets/{npc_key}/{technique}/train_clean.jsonl
subjects/datasets/{npc_key}/{technique}/validation.jsonl
subjects/datasets/{npc_key}/{technique}/train_manifest.json
```

Active techniques:

- `template`
- `docs`
- `ollama`
- `openai`
- `anthropic`

Minimum examples per category:

| Category | Minimum | Current recommended |
| --- | ---: | ---: |
| `identity` | 8 | 12 |
| `teaching` | 32 | 56 |
| `dialogue` | 16 | 32 |
| `quest` | 8 | 16 |
| `refusal` | 8 | 16 |

Every SFT JSONL row must include:

- `messages`: ChatML role sequence beginning with `system`, then user/assistant turns.
- `metadata.npc_key`: snake_case NPC key.
- `metadata.technique`: one active technique.
- `metadata.split`: `train`, `validation`, or `test`.
- `metadata.category`: one of `identity`, `teaching`, `dialogue`, `quest`, `refusal`.
- `metadata.concept`: non-empty concept label grounded in the spec or reference doc.
- `metadata.difficulty`: `beginner`, `intermediate`, or `advanced`.
- `metadata.source`: generation source such as `template`, `docs`, or `ollama:<generator>`.
- `metadata.content_hash`: content hash for deduplication.
- `metadata.generator_params`: object with generation settings.
- `metadata.safety_tags`: array, empty when not applicable.

## 4. Quality Gate

Before training:

```bash
./ucore validate-spec subjects/{npc_key}.json --generation-ready
./ucore generate subjects/{npc_key}.json --technique template
./ucore sanitize subjects/datasets/{npc_key}/template/train.jsonl \
  --output subjects/datasets/{npc_key}/template/train_clean.jsonl \
  --strict-canonical \
  --require-complete-metadata
./ucore dataset-eval subjects/{npc_key}.json --technique template --judge-model qwen2.5:7b
```

Use `quality_failures.json` as the build-loop source of truth. Fix generation,
reference docs, prompts, or category/concept coverage. Do not lower thresholds
or delete failing rows as the first response.

## 5. RL Dataset Requirements

RL dataset generation is schema-ready but not yet an active `ucore` generator.
When implemented, it must use the cleaned SFT data and eval failures as inputs.

Preference pairs:

```text
subjects/datasets/{npc_key}/{technique}/rl/preferences.jsonl
```

- Schema: `subjects/schemas/rl_preferences_record.schema.json`
- Must contain `prompt`, `chosen`, `rejected`, and metadata.
- Should prioritize refusal boundaries, misconception correction, and tone improvements.

Reward rollouts:

```text
subjects/datasets/{npc_key}/{technique}/rl/reward_rollouts.jsonl
```

- Schema: `subjects/schemas/rl_reward_rollout_record.schema.json`
- Must contain `prompt`, `response`, `scores.overall`, and metadata.
- Scores must come from a local judge unless the user explicitly allows cloud evaluation.
