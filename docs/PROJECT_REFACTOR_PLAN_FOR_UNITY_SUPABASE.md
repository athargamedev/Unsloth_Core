# Unsloth_Core Refactor Plan for Reliable Dataset/Training/Eval Pipeline

Goal
Create a clean, stable, experiment-friendly project structure so you can: (1) generate high-quality datasets with multiple techniques/settings, (2) run reproducible training experiments, (3) compare runs objectively, and (4) deploy best GGUF outputs into your Unity NPC dialogue stack backed by Supabase.

Scope
- In scope: repository structure, naming conventions, pipeline contracts, experiment tracking, evaluation workflow, Supabase integration boundaries, Unity deployment handoff.
- Out of scope: changing NPC pedagogical content itself, large model architecture changes, cloud infra redesign.

Current scan findings (from this repo)
1) Documentation mismatch at root:
   - README.md is Supabase CLI upstream content, not Unsloth_Core project docs.
   - Impact: onboarding confusion + wrong commands.

2) Mixed legacy/new path conventions still present in scripts:
   - scripts contain references to legacy flat datasets and mixed output/export paths.
   - Impact: brittle automation and hard-to-debug pipeline behavior.

3) Config duplication risk:
   - Both top-level config variants and presets/ exist; naming overlap can confuse source of truth.
   - Impact: unclear override precedence and accidental wrong runs.

4) Artifact boundary not consistently enforced:
   - outputs/, exports/, eval/ responsibilities are clear in intent but inconsistently referenced.
   - Impact: model provenance and deployment confusion.

5) Environment/vendor noise in repo root:
   - unsloth_env/, caches and generated artifacts can mask project signal.
   - Impact: navigation friction and risk of accidental commits.

6) Good foundation already exists:
   - _config/paths.py centralizes many conventions.
   - goals/project-structure-refactoring/plan.md already has broad migration direction.

Target architecture (single source of truth)
1) Canonical directories
- subjects/{npc_key}.json
- subjects/datasets/{npc_key}/{technique}/{split}.jsonl
  - technique: onyx | ollama | template
  - split: train.jsonl | validation.jsonl
- outputs/{npc_key}/runs/{run_id}/
  - adapter/checkpoints/config snapshot/metrics/TB logs
- exports/{npc_key}/
  - deployable GGUF + manifest.json only
- eval/
  - training-metrics/, reports/{npc_key}/, comparisons/, results/
- supabase/
  - migrations and schema docs only (no app runtime artifacts)

2) Naming contracts
- npc_key: snake_case, stable ID (single source from subject spec)
- run_id: YYYYMMDD_{preset}_{seq3}
- gguf: {npc_key}-{model_short}-{quant}.gguf
- dataset technique folder always explicit (never implied by filename suffix)

3) Contract-first CLI behavior
- ucore becomes the canonical entrypoint.
- scripts remain internal modules/invokables but follow shared contract definitions.
- All path derivation must route through _config/paths.py.

Execution plan (phased)

Phase 0 — Baseline and safety (Day 0)
- Freeze current state:
  - create branch: refactor/structure-naming-reliability
  - collect baseline smoke run for one NPC (chemistry_instructor)
  - snapshot current eval metrics for regression comparison
- Add/verify guardrails:
  - strict .gitignore for envs/caches/large artifacts
  - optional pre-commit checks for path convention lint

Phase 1 — Documentation reset (Day 0-1)
- Replace root README.md with project-native guide:
  - quick start (dataset → train → export → evaluate)
  - canonical folder map
  - command matrix (ucore-first)
  - Unity + Supabase integration section
- Keep detailed workflow docs under docs/ (NotebookLM, Ollama, Training, Eval, Export).

Phase 2 — Configuration normalization (Day 1)
- Define single config hierarchy:
  - base config + preset overlays + CLI overrides
- Remove ambiguity:
  - deprecate duplicate/legacy preset naming paths
  - enforce one preset registry (configs/presets/*)
- Add config validation command:
  - dry-run that prints resolved effective config and paths

Phase 3 — Dataset pipeline normalization (Day 1-2)
- Enforce subjects/datasets/{npc_key}/{technique}/train|validation.jsonl.
- Remove legacy filename suffix logic from generation/training/eval flows.
- Add dataset manifest per generated set (optional but recommended):
  - npc_key, technique, generation timestamp, source model/tool, row counts, hash
- Add dataset quality gate command before training:
  - schema validation, empty-turn checks, role checks, leakage checks.

Phase 4 — Experiment tracking reliability (Day 2)
- Run-centric structure is mandatory:
  - outputs/{npc_key}/runs/{run_id}/... as immutable record
- Persist metadata for each run:
  - resolved config, git commit (if git present), dataset pointers/hashes, key metrics
- Maintain convenience symlinks:
  - outputs/{npc_key}/latest and outputs/{npc_key}/best

Phase 5 — Export and Unity handoff hardening (Day 2-3)
- exports/ holds only deployable artifacts.
- Standardize export manifest.json schema for Unity tooling:
  - npc_key, model_id, model_short, quant, run_id, dataset technique, eval summary
- Ensure deploy_to_unity reads manifest instead of guessing metadata.
- Add deployment validation:
  - verify target path exists (Assets/StreamingAssets/Models/)
  - verify file checksum pre/post copy.

Phase 6 — Evaluation + comparison framework (Day 3)
- Standardize evaluations:
  - smoke (fast), validation set metrics, optional judge rubric
- Save machine-readable outputs to eval/results/*.jsonl.
- Add compare command (run-vs-run, preset-vs-preset, technique-vs-technique).
- Define promotion rule:
  - model promoted to best only if thresholds pass (quality + safety + stability).

Phase 7 — Supabase integration reliability (Day 3-4)
- Separate training artifacts from runtime data concerns.
- Define explicit compatibility checklist before Unity deployment:
  - NPC key alignment with npc_profiles
  - prompt/persona mapping consistency
  - expected memory behavior tests with dialogue_sessions/dialogue_turns
- Add minimal integration test harness:
  - send fixed dialogue probes, verify retrieval/memory behavior consistency.

Phase 8 — Cleanup + migration completion (Day 4)
- Migrate remaining legacy files/paths.
- Remove dead scripts/references after verification.
- Final end-to-end acceptance run:
  - generate → sanitize → train → export → evaluate → deploy manifest check.

Acceptance criteria
- Root README is fully project-accurate and ucore-centric.
- No script writes datasets outside subjects/datasets/{npc_key}/{technique}/.
- No deployable GGUF stored in outputs/ (exports only).
- Every training run has immutable run_id folder + config snapshot + metrics.
- compare workflow can rank at least 2 runs for same NPC.
- Unity deploy step consumes manifest and passes checksum validation.
- Supabase compatibility checklist completed for target NPC before promotion.

Suggested implementation order for minimal disruption
1) Docs + guardrails
2) Config normalization
3) Dataset path normalization
4) Run tracking hardening
5) Export/deploy hardening
6) Evaluation/compare
7) Supabase integration tests
8) Legacy cleanup

Risk controls
- Keep backward-compatible read logic temporarily, but write only to canonical structure.
- Feature-flag destructive migration steps.
- Preserve one rollback snapshot before each phase.

Deliverables
- Updated README + docs/* workflows
- Canonical path and naming contract docs
- Updated scripts/ucore behavior aligned to contracts
- Migration notes with before/after mapping
- Verified baseline and post-refactor comparison report

Immediate next 3 actions (practical)
1) Replace README.md with Unsloth_Core project guide.
2) Run a grep-based path audit and patch all legacy dataset/output/export references.
3) Add a run-metadata manifest writer to training so every run is reproducible and comparable.
