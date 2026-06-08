---
last_verified: 2026-06-08
next_audit: 2026-07-05
---

# Unsloth_Core Project State

## Mission

Build GGUF LoRA adapters for llama3.2 3B NPCs. Unity/LLMUnity loads one shared base GGUF and swaps lightweight LoRA adapter GGUFs plus NPC system prompts. Local Supabase supports dialogue/session state.

## Active NPCs

Only these are active for prototype validation:

- `history_guide` — world history
- `chef_assistant` — culinary arts

If old docs mention other NPCs as active, treat that as deprecated unless the user explicitly reactivates them.

## Current verified run state

Verified 2026-06-08:

- `chef_assistant` latest/best now point to `artifacts/models/chef_assistant/runs/20260608_safe-any_llama3.2-3b_003`.
- `chef_assistant` density/specificity repair rewrote weak runtime concepts to 35–55 word / 2–3 sentence examples and added exact eval prompts for kitchen workflow, food safety, cooking techniques, ingredient science, and knife skills.
- `chef_assistant` repaired clean dataset: 175 rows, structural `dataset-eval` status `ok`, semantic fast gate 4/5 (80%). Remaining fast-gate miss is one identity constraint score; no structural block.
- `chef_assistant` low-VRAM density variant: `fast-3b` with `max_seq_len=512`, `batch_size=1`, `grad_accum=8`, `lora_r=8`, `lora_alpha=16`, `packing=false`, `train_on_responses=true`, `UNSLOTH_DISABLE_STATISTICS=1`; final loss 1.3825.
- `chef_assistant` adapter exported: `artifacts/exports/chef_assistant/chef_assistant-lora-f16.gguf` (24.3 MB).
- Runtime eval full-spec result: `artifacts/eval/reports/chef_assistant/eval_20260608T150804_824838Z.html`; base+LoRA CPU eval (`--gpu-layers 0`), Ollama judge `qwen2.5:7b` active, `--runtime-sentence-guard`, 19 examples, candidate 17W/2L/0T (89.5%). Candidate avg words 34.3 vs baseline 44.8; candidate avg sentences 2.6; zero runtime constraint violations.
- Canonical feedback JSON now points at the full-spec guarded eval: `artifacts/eval/results/feedback/chef_assistant.json`; weak concept list is only `dialogue/flavor balance` (one baseline win, no constraint violation).
- Professional report bundle: `artifacts/reports/chef_assistant/chef_assistant_npc-production-grounded_ollama_evaluate/` with `summary.md`, `index.html`, `pipeline_run_spec.json`, `stage_status.json`, `integration_health.json`, `dataset_quality.json`, `runtime_eval_report.json`, `training_report.json`, `next_actions.json`; `runtime_eval_report.json` now reflects the 19-example guarded eval.
- `history_guide` remains on promoted run `20260607_fast-1.7b_llama3.2-3b_002` unless a later verified run supersedes it.

## Dataset generation policy

- Template generation is smoke/dev only.
- Never train production LoRA on template data.
- Production data must use the approved grounded workflow. NotebookLM is deprecated — do not use for production.
- **Use `./ucore generate-ollama` for production generation.** `./ucore generate --technique ollama` is deprecated (hits legacy path via `_generate_shared.py`).
- Feedback loop: `./ucore feedback --auto` now uses `generate-ollama --concept-focus` + `sanitize` + `dataset-eval` — the actively-maintained CLI pipeline. The old 1305-line feedback loop was refactored to ~350 lines.

## Canonical workflow

Primary agent/operator path (preferred):

```bash
source unsloth_env/bin/activate
./ucore target plan --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate
./ucore target run --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate --resume
```

Manual recovery commands (advanced):

```bash
source unsloth_env/bin/activate
./ucore audit check
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
# Production generation (use generate-ollama, NOT generate --technique ollama)
./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
# Template is smoke/dev only:
# ./ucore generate data/npcs/specs/<npc>.json --technique template
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --mode fast --judge-model qwen2.5:7b
./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf
./ucore evaluate --baseline <base-or-baseline-gguf> --candidate <adapter-or-run> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html \
  --runtime-sentence-guard
```

### Scripts location

All pipeline scripts live in `src/core/` (organized by function: `dataset/`, `training/`, `evaluation/`, `export/`, `ops/`). The old `scripts/` was a symlink to `src/core/` — removed to eliminate confusion. Use `./ucore` to run all pipeline commands.

### CLI structure

The CLI (`src/cli/ucore`) exposes ~38 commands. The canonical pipeline uses only 6:

1. `validate-spec` → 2. `generate-ollama` → 3. `sanitize` → 4. `dataset-eval` → 5. `train` (+ `--export-gguf`) → 6. `evaluate`

Dead/deprecated commands are marked `[LEGACY]`, `[DEPRECATED]`, or `[EXPERIMENTAL]` in the help text. See the Simplification report at `docs/dataflow-report.md` for details.

## Quality gate

- Training expects `train_clean.jsonl`.
- Gate artifacts live beside the dataset:
  - `quality_summary.json`
  - `quality_failures.json`
- The training gate checks exact dataset hash, distribution gaps, unknown rows, sanitizer signals, and summary status.
- `--allow-ungated-dataset` is dev-only, not production.

## Canonical paths

- Specs: `data/npcs/specs/<npc>.json`
- Reference docs: `data/npcs/reference_docs/<npc>_primer.md`
- Datasets: `data/datasets/<npc>/<technique>/`
- Training runs: `artifacts/models/<npc>/runs/<run_id>/`
- Pointers: `artifacts/models/<npc>/best`, `artifacts/models/<npc>/latest`
- GGUF adapters: `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- Reports: `artifacts/eval/reports/<npc>/`
- Feedback JSON: `artifacts/eval/results/feedback/<npc>.json`
- Unity project: `~/Setup Guide In-Editor Tutorial/`
- Unity model folder: `Assets/StreamingAssets/Models/`

## Local services

- Supabase: check with `python src/core/ops/docker_core_status.py`; start with the repo's Docker Compose/Supabase workflow when needed.
- Current Docker core project: `LLM_WSL`.
- Current local ports:
  - Supabase DB: `15433`
  - Supabase API/Kong: `16433`
  - Supabase Studio: `16434`
  - Supabase Analytics: `16435`
  - Supabase Inbucket: `16436`
- Last verified 2026-06-08: Docker core services were down (0/11 up). Start before tracked eval/session persistence work.
- Dashboard package: `src/dashboard/unity-npc-llm-training-dashboard/`
- Dashboard dev: `cd src/dashboard/unity-npc-llm-training-dashboard && npm run dev`
- Dashboard port: `3100`

## Local machine constraints

- Local GPU is RTX 3060-class 6GB VRAM.
- Unload Ollama before train/eval if it holds VRAM.
- Local tested Ollama judge/default: `qwen2.5:7b`.
- Preflight may downgrade `fast-3b` to `safe-any` on low VRAM.
- Triton/Unsloth training may need `gcc` and `as` on PATH.

## Deprecated / avoid

- Do not describe `astronomy_guide` or `fitness_coach` as active.
- Do not present template datasets as production-ready.
- Do not use `qwen3:latest` as a confirmed local default unless re-verified.
- Do not treat adapter GGUFs as standalone full merged models; evaluate with base + LoRA when needed.
- Do not lower thresholds or delete rows to force a green gate.
- Do not claim W&B/Confident upload unless local output or URL proves it.

## Agent instructions-files strategy (active 2026-06-05)

A 5-tier hierarchy ensures single-fact-single-place knowledge with automated freshness:

| Tier | What | Where |
|------|------|-------|
| T0 Entrypoint | Hard rules & quickstart | `AGENTS.md`, `README.md` |
| T1 Onboarding | Dev/AI setup guide | `CONTRIBUTING.md`, `SETUP.md` |
| T2 Canonical Reference | State & workflow docs | `docs/project-state.md`, `docs/training-workflow.md` |
| T3 Skills/Procedures | Reusable workflows | `.hermes/skills/`, `.codex/skills/` |
| T4 Agent Briefs | Role-specific guides | `.hermes/agents/`, `.codex/agents/` |

**Rules:**
- Every skill/agent brief MUST have `last_verified: YYYY-MM-DD` in YAML frontmatter
- Skills reference canonical files (T0/T2), never copy their content
- **Compatibility symlinks removed** (June 2026 cleanup): `configs`, `frontend_control`, `outputs`, `exports`, `eval`, `logs`, `_config`, `.pipeline`, `subjects/schemas`, `ucore`. All replaced by canonical paths (`etc/`, `artifacts/`, `var/.pipeline/`, `src.cli.ucore`).
- Shared knowledge (e.g. context maintenance) lives in one skill, not duplicated across `.hermes` and `.codex`

**Baseline cleanup (Phase 1 complete 2026-06-05):**
- Patched legacy `subjects/` paths → `data/` and `artifacts/` in `.hermes/skills/unsloth-core-operator/SKILL.md` and `.hermes/memories/unsloth_core_project_memory.md`
- Removed deprecated NotebookLM references
- Added `last_verified: 2026-06-05` frontmatter to all 18 agent guidance files
- Standardised YAML frontmatter format (name, description, last_verified) on all agent briefs
- Fixed stale `docs/index.md` paths
- Updated this file (last_verified date, NotebookLM deprecation, strategy section)

**Files stamped with freshness (18 total):**
- Hermes skills (5): unsloth-core-operator, unsloth-core-context-maintenance, unsloth-core-low-vram-training, unsloth-core-test-coherence, llmunity-runtime-deploy
- Codex skills (6): unsloth-core-pipeline-agent, unsloth-core-operator, unsloth-core-context-maintenance, unsloth-core-low-vram-training, unsloth-core-dashboard, llmunity-runtime-deploy
- Hermes agents (4): frontend-dashboard-agent, dataset-eval-repair-agent, training-export-eval-agent, unity-runtime-agent
- Codex agents (1): ucore-pipeline-chief
- Codex subagents (8): context-sentinel, dashboard-unity-verifier, dataset-generation-engineer, gguf-unity-exporter, regression-reviewer, runtime-eval-feedback-engineer, sanitizer-gate-engineer, spec-grounding-curator, training-vram-engineer

**Completed phases (P1–P10):**
- P1 Config coherence — `./ucore audit config-coherence --json` green
- P3 Judge cache integration — manifest stats, dataset-eval flags
- P4 Inference/GPU lifecycle — GpuLeaseManager, lease/release endpoints
- P5 Target runner — plan schema + dry-run/resume execution
- P6 Experiment/run registry — local JSONL registry, hook capture, compare+promote CLI
- P7 Dashboard truthfulness — artifact-registry-backed status, command schema parity
- P8 NPC component contracts — Pydantic Identity/Tone/Grounding/Refusal/Runtime/Distribution
- P9 Docs/context cleanup — qwen3→qwen2.5 defaults across 7 docs, inactive NPC examples replaced, stale paths fixed, operator-runbook path corrections
- P10 Production pilot (updated 2026-06-08):
  - Both active NPCs have trained/exported/evaluated evidence in `artifacts/`.
  - `history_guide`: promoted run `20260607_fast-1.7b_llama3.2-3b_002`, final loss 1.6116, prior runtime eval 55.6% win rate (5W/2L/2T).
  - `chef_assistant`: latest/best run `20260608_safe-any_llama3.2-3b_003`, final loss 1.3825 after density/specificity repair and low-VRAM retrain.
  - `chef_assistant` runtime density eval: `runtime_eval_density_20260608.json`, 10 examples, candidate 10W/0L/0T (100%); candidate avg 37 words vs baseline 84; one food-safety response still had a 4-sentence violation despite winning.
  - GGUF adapters exported to `artifacts/exports/<npc>/<npc>-lora-f16.gguf`.
  - Base+LoRA eval uses CPU fallback (`--gpu-layers 0`) on this 6GB VRAM machine.
  - Professional bundle reports live under `artifacts/reports/<npc>/<run_id>/`.
  - 3 bugs fixed in legacy generate_dataset.py (import error, url=None crash, async fallback)
  - Fixed `dataset_eval.py` L107 and L607-608 — both `dataset_dir()` and error message now use `dataset_root()` not hardcoded `subjects/datasets/`
  - Cleared stale quality artifacts from `subjects/datasets/`
  - All changes committed

**Completed phases (Context):**
- Create standard agent brief template
- Create CONTRIBUTING.md, SETUP.md, proper README.md
- Deduplicate split skills (`.hermes` vs `.codex` context-maintenance)

**Remaining work:**
- P2 Train-gate hardening — make ArtifactRegistry lineage properly block on stale/missing input signatures
- Walk through SETUP.md from fresh clone
- Regenerate history_guide dataset via proper `./ucore generate-ollama` path (currently forced to template due to `_is_history_subject()` in ollama_orchestrator.py)
- GPU eval OOM — investigate running llama-server with partial offload (`--gpu-layers` < 99) to fit both base + LoRA on 6GB
- Address 104+ stale `subjects/` path references across source code (tech debt)
