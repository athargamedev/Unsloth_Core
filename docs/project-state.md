---
last_verified: 2026-06-07
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

## Dataset generation policy

- Template generation is smoke/dev only.
- Never train production LoRA on template data.
- Production data must use the approved grounded workflow. NotebookLM is deprecated — do not use for production.
- **Use `./ucore generate-ollama` for production generation.** `./ucore generate --technique ollama` hits the legacy `generate_dataset.py` path (documented as fallback in its own header) and has known bugs fixed in the current commit.
- The legacy `generate_dataset.py` module header states: *"Active production generation should use generate_dataset_ollama.py."*

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
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
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

- Supabase: start with `supabase start`
- Supabase DB: `15434`
- Supabase API/Kong: `16437`
- Supabase Studio: `16438`
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
- Stale paths (`subjects/`, `outputs/`, `exports/`) are deprecated — use `data/`, `artifacts/` everywhere
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
- P10 Production pilot (completed 2026-06-07):
  - Both NPCs trained and evaluated end-to-end:
    - `history_guide`: run `20260607_fast-1.7b_llama3.2-3b_002`, final loss 1.6116, GGUF 48,655,200 bytes
    - `chef_assistant`: run `20260607_fast-1.7b_llama3.2-3b_004`, final loss 1.2203
  - Both runs promoted (best/latest point to current run)
  - GGUF adapters exported to `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
  - Evaluation: history_guide 55.6% win rate (5W/2L/2T), chef_assistant 50.0% win rate (5W/5L/0T)
  - Both evals used CPU fallback (`--gpu-layers 0`) due to GPU OOM on 6GB VRAM
  - HTML reports: `artifacts/eval/reports/<npc>/eval_20260607T*.html`
  - Feedback JSONs: `artifacts/eval/results/feedback/<npc>.json`
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
