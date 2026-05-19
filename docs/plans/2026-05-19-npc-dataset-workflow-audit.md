# NPC Dataset Workflow Audit

> Phase 1 audit for the dataset generation / sanitization / validation / DeepEval loop.

**Scope:** NPC specs, reference primers, dataset generation, sanitization, validation, DeepEval, feedback loop, and artifact layout.

---

## What I reviewed

- `subjects/NPC_specs/*.json`
- `subjects/reference_docs/*.md`
- `subjects/schemas/sft_record.schema.json`
- `scripts/generate_dataset.py`
- `scripts/sanitize_dataset.py`
- `scripts/validate_subject_spec.py`
- `scripts/dataset_eval.py`
- `scripts/feedback_loop.py`
- `tests/evals/test_dataset_generation_quality.py`
- `tests/evals/metrics.py`

---

## Current-state findings

### 1) The spec contract exists, but it is only partially machine-enforced

Each NPC spec already includes the core fields we need:
- `identity`
- `teaching`
- `dialogue`
- `quest`
- `refusal`
- `reference_doc`
- `system_prompt`
- `research_queries`
- `dataset`
- `concepts`

That is a good foundation, but the automation is still only loosely coupled to those fields.

Observed gap:
- generation and evaluation still rely on a mix of spec content, helper scripts, and category templates
- there is no single end-to-end contract object that binds spec → generation → sanitize → validate → DeepEval → feedback

Impact:
- the workflow can run, but it is not yet self-adjusting or strongly provenance-aware

### 2) Reference docs mostly meet the primer contract, but the contract itself is unevenly surfaced

The four NPC primers are strong and already have the right shape:
- >250 words
- multiple H2 sections
- many concrete bullets
- safety/refusal/boundary notes

But the top-level `subjects/reference_docs/README.md` is only a minimal contract note and currently contains a placeholder marker, not a full review protocol.

Impact:
- the primers are useful for generation, but the repository does not yet give a single authoritative operator-facing checklist for how to improve them

### 3) Dataset generation still behaves like a template-first scaffold, not a quality-optimized loop

`generate_dataset.py` is capable of emitting all five required categories:
- identity
- teaching
- dialogue
- quest
- refusal

It also has checkpointing and some paraphrase variation, which is good.

However:
- the generation shapes are still mostly template-driven
- the current script does not appear to encode a strong distribution policy for category balance, difficulty mix, or concept coverage
- the code is focused on producing rows, not on optimizing for the best structure/format/distribution across iterations

Impact:
- the generator can make usable data, but it does not yet automatically converge toward a better dataset shape

### 4) Sanitization is strong on formatting, but weak on dataset-structure feedback

`sanitize_dataset.py` already does useful work:
- strict structural validation
- artifact filtering
- scoring/enrichment
- metadata normalization

This is good, but the current design still mostly answers: “is this row clean?”
It does not yet clearly answer: “is the dataset distribution healthy?”

Impact:
- clean rows can still produce a weak dataset if the category balance, concept variety, or refusal quality is poor

### 5) Validation exists, but it is split between spec readiness and dataset shape

`validate_subject_spec.py` is already enforcing useful checks:
- valid NPC key naming
- reference doc presence and location
- reference doc length/structure quality
- supported dataset categories
- system prompt constraints
- `dataset.examples_per_category`

This is the right direction, but the validation model still needs a clearer separation between:
- spec readiness
- dataset schema correctness
- dataset distribution quality
- downstream training usefulness

Impact:
- validation is present, but it is not yet a full gate for “ready to generate, train, and improve.”

### 6) DeepEval is already useful, but its output is not yet a first-class control signal

`dataset_eval.py` already writes:
- `quality_summary.json`
- `quality_failures.json`

and the DeepEval tests already score:
- persona/category fit
- training usefulness/specificity
- faithfulness / relevancy / contextual precision
- role adherence / retention / completeness
- safety metrics

This is promising.

Observed gap:
- the feedback loop is still mostly a “read the report and regenerate” tool
- it does not yet appear to transform failure patterns into a richer policy for what to change next

Impact:
- the loop can detect problems, but it does not yet reliably self-correct toward an optimal distribution

### 7) Feedback loop logic exists, but it is still concept-level rather than distribution-level

`feedback_loop.py` already:
- identifies weak concepts
- uses thresholds for win rate / quality / violations
- can regenerate examples
- can optionally auto-retrain
- updates shared pipeline state

But the current logic is concept-focused, not yet a full dataset-shaping engine.

Missing pieces:
- distribution targets by category/difficulty/concept
- duplicate / near-duplicate pressure checks
- systematic answer-length / refusal-quality balancing
- a clear retry budget and stop condition based on improvement plateau

Impact:
- the loop is useful, but not yet robust enough to “hunt the ideal structure” on its own

### 8) The schema is strict on row metadata, but it does not yet encode all of the feedback-loop variables

The SFT schema already requires metadata fields such as:
- npc_key
- technique
- split
- category
- concept
- difficulty
- source
- content_hash
- generator_params
- safety_tags

That is good.

What is still missing is a richer contract for:
- spec version / primer version
- generation iteration id
- evaluation lineage
- whether the row was regenerated due to a known failure mode
- distribution bucket / target bucket

Impact:
- the system can validate rows, but it cannot yet fully reason about why a row exists or what improvement cycle produced it

---

## Concrete blockers to automate the workflow well

1. No single canonical pipeline contract object linking spec → dataset → sanitize → validate → eval → feedback.
2. No explicit distribution policy for category balance, difficulty spread, or concept coverage.
3. DeepEval results are available, but the feedback loop does not yet convert them into a structured correction policy.
4. The row schema does not fully capture iteration/provenance/distribution metadata.
5. The sanitizer validates structure, but not enough quality-shaping signals.
6. The system lacks a clear plateau/stop rule for repeated regeneration attempts.

---

## Recommended target shape

The workflow should eventually behave like this:

1. Validate spec readiness.
2. Generate a candidate dataset.
3. Sanitize and attach provenance.
4. Validate structure and distribution.
5. Run DeepEval.
6. Convert failures into one of a small set of actions:
   - add more examples
   - rebalance categories
   - rewrite primer/spec
   - fix format/sanitizer
   - stop and escalate
7. Repeat only if measurable improvement is likely.

---

## Immediate next implementation targets

1. Add a machine-readable generation manifest that records spec version, technique, iteration, and target distribution.
2. Extend validation to check distribution shape, not just required fields.
3. Convert DeepEval failures into a small action taxonomy.
4. Add plateau detection so the loop stops when it is no longer improving.
5. Surface the entire workflow as one orchestration command.

---

## Next step

Move to Phase 2: define the exact machine-readable contracts for spec, dataset, sanitization, and evaluation.
