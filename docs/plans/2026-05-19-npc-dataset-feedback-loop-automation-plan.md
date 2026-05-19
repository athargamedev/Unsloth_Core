# NPC Dataset Feedback Loop Automation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a repeatable, mostly automated workflow that reviews NPC specs, generates datasets, sanitizes and validates them, runs DeepEval, and feeds failures back into the next generation cycle until the dataset structure, format, distribution, and coverage are strong enough to improve training quality.

**Architecture:** Treat the NPC spec as the contract, the generated dataset as an artifact, and DeepEval failures as the feedback signal. The workflow should be a backend-first pipeline with one canonical job state, deterministic intermediate outputs, and a clear stop/go decision after each stage. Humans should only intervene when the loop cannot self-correct within a budget or when the system detects a missing reference/knowledge gap.

**Tech Stack:** `ucore`, Python pipeline scripts, JSON Schema validation, DeepEval/Ollama judge, repo docs under `subjects/reference_docs/`, and the dashboard/job registry for visibility.

---

## Current-State Findings to Review First

Before changing behavior, inspect the existing workflow and record where each contract lives:
- NPC spec source of truth: `subjects/NPC_specs/{npc_key}.json`
- Dataset generation entrypoints: `scripts/generate_dataset.py` and `./ucore generate`
- Sanitization: `scripts/sanitize_dataset.py` and `./ucore sanitize`
- Generation-readiness validation: `./ucore validate-spec <spec> --generation-ready`
- Dataset quality gate: `scripts/dataset_eval.py`, `tests/evals/`, and `./ucore dataset-eval`
- Feedback loop / gap analysis: `scripts/feedback_loop.py`, `scripts/evaluate.py --feedback-json`
- Reference grounding: `subjects/reference_docs/README.md` and the per-NPC primer docs
- Runtime outputs: `subjects/datasets/{npc}/{technique}/`, `outputs/{npc_key}/`, `eval/`

The review should answer:
1. Are the NPC specs precise enough to generate good data consistently?
2. Do generated datasets cover the intended categories and styles evenly?
3. Does sanitization preserve useful examples while enforcing canonical structure?
4. Does validation reject malformed or low-signal rows early?
5. Does DeepEval identify the right failures, and can those failures drive the next generation pass?

---

## Canonical Target Contracts

### 1) Spec contract
Each NPC spec must clearly define:
- persona and identity boundaries
- allowed domain knowledge
- refusal boundaries and safe redirects
- required dataset categories
- minimum examples per category
- style/voice constraints
- canonical file paths for outputs

### 2) Dataset contract
Every row should be machine-checkable and preserve provenance:
- NPC key
- generation technique
- category
- prompt / response pair or ChatML messages
- source/spec version
- reference-doc or concept tag when applicable
- safety / refusal tags when applicable
- a stable schema version field

### 3) Sanitization contract
Sanitization must be deterministic and non-destructive by default:
- normalize whitespace and role labels
- enforce ChatML shape
- reject empty or malformed rows
- preserve metadata
- never silently rewrite meaning
- emit a report of removed/changed rows

### 4) Validation contract
Validation should fail fast on:
- missing categories
- missing required metadata
- poor distribution across categories
- malformed message structure
- spec/dataset path mismatches
- examples that are too vague, too repetitive, or off-domain

### 5) DeepEval contract
DeepEval should score and report:
- persona fit
- domain correctness
- factual reliability
- conversation usefulness
- refusal quality
- category balance / coverage
- format compliance
- improvement deltas versus the previous dataset version

### 6) Feedback contract
The feedback loop should translate failures into one of a few action types:
- regenerate more examples for a weak category
- rewrite the spec or primer if the issue is conceptual
- add missing reference docs if knowledge is absent
- change sanitization rules if formatting is masking good data
- stop and request human review if the loop is stuck

---

## Phased Execution Plan

### Phase 1: Audit and map the workflow

**Objective:** Create an evidence-backed map of the current pipeline and identify the bottlenecks that prevent automation.

**Files to inspect:**
- `subjects/NPC_specs/*.json`
- `subjects/reference_docs/*.md`
- `scripts/generate_dataset.py`
- `scripts/sanitize_dataset.py`
- `scripts/dataset_eval.py`
- `scripts/feedback_loop.py`
- `scripts/evaluate.py`
- `tests/evals/*`
- `docs/NPC_DATA_RL_EXECUTION_CONTRACT.md`

**Tasks:**
1. Enumerate what each step currently consumes and emits.
2. Document the exact dataset schema and any implicit assumptions.
3. Identify where structure/format/distribution are currently being guessed instead of measured.
4. Record the existing DeepEval failure categories and how they map to action items.
5. Produce a short findings report with the biggest automation blockers.

**Done when:**
- We can describe the full pipeline end-to-end without ambiguity.
- Every output path and artifact type is listed.
- The current sources of truth are explicit.

---

### Phase 2: Define the machine-readable contracts

**Objective:** Make the spec, dataset, sanitization, and evaluation boundaries explicit so the workflow can be automated safely.

**Files to create or modify:**
- `subjects/schemas/*.json` (dataset and feedback schemas if missing or incomplete)
- `subjects/reference_docs/README.md`
- `scripts/generate_dataset.py`
- `scripts/sanitize_dataset.py`
- `scripts/dataset_eval.py`

**Tasks:**
1. Add or refine schema fields for metadata, provenance, and versioning.
2. Add a strict notion of required categories and minimum counts.
3. Define canonical naming for dataset splits and technique folders.
4. Make sanitization emit a structured summary of the transformations it performed.
5. Make validation return actionable failure reasons, not just pass/fail.

**Done when:**
- The pipeline can reject invalid inputs before generation.
- The generated dataset can be traced back to a spec version and technique.
- The sanitizer and validator both emit structured reports.

---

### Phase 3: Build an automated review loop around DeepEval

**Objective:** Use DeepEval as a feedback signal that tells the system what to regenerate or rewrite next.

**Files to create or modify:**
- `scripts/feedback_loop.py`
- `scripts/dataset_eval.py`
- `tests/evals/*`
- `./ucore` command wiring if needed

**Tasks:**
1. Normalize DeepEval outputs into a compact failure taxonomy.
2. Map each failure type to a next action:
   - regenerate category examples
   - improve spec/primer
   - add missing factual grounding
   - fix formatting/sanitization
3. Add a budgeted retry loop with a hard stop condition.
4. Compare dataset versions so the loop can measure improvement, not just absolute score.
5. Make the loop write a clear artifact showing why it stopped or succeeded.

**Done when:**
- DeepEval results can be consumed programmatically.
- The loop can recommend the next step automatically.
- The system stops after a defined number of retries or when improvement stalls.

---

### Phase 4: Add structure/distribution analysis for better dataset quality

**Objective:** Ensure the workflow optimizes the actual distribution, not just raw row count.

**Files to create or modify:**
- `scripts/dataset_eval.py`
- `scripts/feedback_loop.py`
- `tests/evals/*`
- any helper module used for analysis

**Tasks:**
1. Measure category balance and coverage.
2. Detect duplicates, near-duplicates, and template repetition.
3. Measure answer length distribution and refusal quality.
4. Track whether examples are too generic or too overfit to one style.
5. Identify concepts that repeatedly fail across iterations.

**Done when:**
- The pipeline can report distribution problems, not just schema errors.
- The feedback loop can target the weakest category/concept next.

---

### Phase 5: Automate the orchestration entrypoint

**Objective:** Provide one command that runs the whole review/generate/sanitize/validate/eval loop.

**Files to create or modify:**
- `./ucore` command wiring
- orchestration script or pipeline module
- dashboard job integration if needed

**Tasks:**
1. Add a top-level command that runs the workflow end-to-end.
2. Make it accept a spec, technique, and budget/retry limit.
3. Emit intermediate artifacts after every stage.
4. Surface the current phase and next action in job state.
5. Make the command safe to resume after interruption.

**Done when:**
- A single command can drive the workflow without manual file juggling.
- Every stage writes a machine-readable result.
- The dashboard can show the job’s current phase and last failure reason.

---

### Phase 6: Close the loop with regression tests

**Objective:** Prevent the automation from drifting or regressing over time.

**Files to create or modify:**
- `tests/evals/*`
- new pipeline tests for orchestration and artifact contracts
- maybe a smoke test fixture for a known NPC spec

**Tasks:**
1. Add tests for spec readiness.
2. Add tests for sanitization idempotence.
3. Add tests for validation failure messages.
4. Add tests for DeepEval report parsing and action mapping.
5. Add a small end-to-end smoke test that runs the loop on one NPC.

**Done when:**
- The workflow is test-covered at each stage.
- A bad spec or bad dataset cannot silently pass through the system.

---

## Acceptance Criteria

The project is ready when all of the following are true:
- A spec can be reviewed for generation readiness before any dataset work starts.
- Every generated dataset row has clear provenance and metadata.
- Sanitization is deterministic and produces a useful report.
- Validation rejects malformed or low-signal data with actionable errors.
- DeepEval output is machine-readable and maps to corrective actions.
- The system can iterate toward a better dataset distribution instead of only producing more rows.
- The whole process can be run from one orchestration command.
- The workflow is resumable and observable.

---

## Immediate Next 3 Actions

1. Inspect the current NPC specs, reference docs, and dataset scripts to build the workflow map.
2. Define the exact dataset and feedback schema fields that the automation must preserve.
3. Add the DeepEval-to-action mapping so failures can trigger the right next step automatically.

---

## Resume Protocol

If we continue from this plan later, resume in this order:
1. Phase 1 audit
2. Phase 2 contract definition
3. Phase 3 DeepEval feedback loop
4. Phase 4 distribution analysis
5. Phase 5 orchestration command
6. Phase 6 regression tests

Current phase: planning complete, implementation not started.
