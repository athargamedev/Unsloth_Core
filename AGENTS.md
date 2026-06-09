# Unsloth_Core: Agent Context

Primary source of truth for agents in this repo. Keep this file short and current. Detailed state lives in `docs/project-state.md`; full workflow docs live in `docs/training-workflow.md`.

## Mission

Build high-quality GGUF LoRA adapters for llama3.2 3B NPCs. Unity/LLMUnity loads one shared base GGUF and swaps lightweight LoRA adapter GGUFs plus NPC system prompts. Local Supabase stores dialogue/session state.

## Active project state

- Active NPCs: `history_guide`, `chef_assistant`, `marvel_heroes_instructor`.
- **Latest runs:** `history_guide` run `20260607_fast-1.7b_llama3.2-3b_002` (loss 1.61), `chef_assistant` run `20260607_fast-1.7b_llama3.2-3b_004` (loss 1.22). Both promoted. GGUF exports at `artifacts/exports/<npc>/`. `marvel_heroes_instructor` run `20260609_safe-any_llama3.2-3b_003` (loss 2.95) — Ollama dataset (150 clean rows). GGUF adapter at `artifacts/exports/marvel_heroes_instructor/`.
- **Eval results:** history_guide 5/9 wins (55.6%), chef_assistant 5/10 wins (50.0%). GPU OOM forced CPU fallback (`--gpu-layers 0`).
- **Bug fixed:** `dataset_eval.py` both `dataset_dir()` function and error message now use canonical `dataset_root()` instead of hardcoded `subjects/datasets/`.
- Production dataset rule: use the current approved grounded workflow. NotebookLM is no longer used. Template generation is smoke/dev only.
- Local tested Ollama judge/default: `qwen2.5:7b` unless a fresh benchmark says otherwise.
- Local GPU: RTX 3060-class 6GB VRAM. Use `~/llama-servers.sh killall` to free VRAM before train/eval. Stale llama-server processes accumulate.
- Process control: `~/llama-servers.sh` manages Cognee's llama.cpp servers (:18080 chat, :18081 embed). Commands: `start|stop|killall|preflight|status`. A cron watchdog auto-cleans stale llama-server processes every 10min.
- **Generation via direct llama.cpp** (more control, no Ollama overhead):
  - `./ucore generate-local --model <gguf> data/npcs/specs/<npc>.json` — auto starts llama.cpp, generates, stops
  - Or two-step: `~/llama-servers.sh serve` then `./ucore generate-ollama --url http://127.0.0.1:<port>/v1/chat/completions`
  - Uses tuned params: gpu-layers 24, ctx-size 8192, batch-size 512, parallel 4
- Dashboard app lives in `src/dashboard/unity-npc-llm-training-dashboard/`.
- Supabase Docker core project: `LLM_WSL`. Current local ports: DB `15433`, API/Kong `16433`, Studio `16434`, Analytics `16435`, Inbucket `16436`.
- **All compatibility symlinks removed:** No `configs`, `frontend_control`, `outputs`, `exports`, `eval`, `logs`, `subjects/schemas`, `_config`, `.pipeline`, or `ucore` symlinks remain. `./ucore` is now a real bash wrapper.
- **Legacy Python import shim removed:** `src/core/__init__.py` no longer exposes top-level compatibility aliases like `src.core.dataset_eval` or `src.core.smoke_test`. Use canonical subpackages only (`src.core.dataset.*`, `src.core.evaluation.*`, `src.core.ops.*`, `src.core.training.*`).

## Hard rules

- Do not train production LoRA on template data.
- Do not mark inactive NPCs as active unless the user reactivates them.
- Do not lower eval thresholds, dataset minimums, or runtime constraints to force a pass.
- Treat `quality_failures.json` as repair input, not something to delete.
- Verify actual repo/tool state before updating docs or memories.
- Keep durable memory compact. Procedures belong in skills.
- Use caveman reporting: Done/Changed/Ran/Result/Blocked/Next.

## Strategy & anti-loop

Production NPC strategy lives in `etc/npc-production-strategy.yaml`. The `npc-production-grounded` profile defines pipeline defaults: technique, dataset density targets, quality gate mode (release/wandb/Confident), training preset, and runtime eval. Use `./ucore strategy --profile npc-production-grounded` to inspect.

The `classify_feedback_cycle()` function implements the anti-loop: after 1 exact Confident failure repair, 1 density repair, and 1 training preset variant per NPC, it escalates to `escalate_shared_strategy` — route the fix to shared pipeline/presets, not another per-NPC cycle.

The `density_repair_needed()` function prevents endless concept patching by checking whether the candidate's avg words fall below 65% of baseline. If terse + weak, route to a bounded density repair profile rather than another concept-patch cycle.

All feedback JSON from `./ucore evaluate --feedback-json` now carries `avg_candidate_words`, `avg_baseline_words`, `avg_candidate_sentences`, `avg_baseline_sentences` for density-aware decisions. `density_repair_needed()` also backward-computes these from per-example data when top-level fields are absent (older evals). Every `./ucore feedback --json` output includes `strategy_decision` (action + flags + counts) and `density_decision` (needed + candidate/baseline words + profile).

Use `--strategy-profile` on `./ucore feedback` to set the profile.

## Quick start

```bash
source unsloth_env/bin/activate

# Health check
./ucore audit check
~/llama-servers.sh preflight   # process/port/VRAM check

# Generation (two options):
#   A) Via Ollama (default)
./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
#   B) Via direct llama.cpp (more control)
./ucore generate-local --model ~/.ollama/models/blobs/sha256-2bada8a7450... \
    data/npcs/specs/<npc>.json --fresh

# Sanitize + gate + train
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json \
  --technique <technique> --mode fast --judge-model qwen2.5:7b
./ucore train data/npcs/specs/<npc>.json \
  --technique <technique> --preset fast-3b --export-gguf

# Target-based pipeline (preferred for multi-stage runs)
./ucore target plan --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate
```

Manual health/spec checks:

```bash
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
```

Dashboard:

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run dev
```

## Artifact naming conventions

All artifacts follow a self-describing naming standard. Every filename should tell you what it is without opening it:

| Artifact | Pattern | Example |
|----------|---------|---------|
| Training run dir | `{date}_{preset}_{model_short}_{seq}` | `20260607_safe-any_llama3.2-3b_001` |
| Eval report file | `[{technique}_][{judge_}]eval_{timestamp}.{fmt}` | `qwen2.5-7b_eval_20260609T120000Z.html` |
| Feedback JSON | `{npc}_{timestamp}.json` + `{npc}.json` → symlink | `chef_assistant_20260609T120000Z.json` → `chef_assistant.json` |
| Report bundle dir | `{profile}_{technique}_{stage}_{timestamp}` | `npc-production-grounded_ollama_evaluate_20260609T120000Z/` |
| GGUF export | `{npc}_lora-{outtype}.gguf` | `chef_assistant_lora-f16.gguf` |
| Dataset quality | `quality_summary.json` (at `data/datasets/{npc}/{technique}/`) | — |

**system_suffix()** — encode external systems in filenames:
- `_C` = Confident AI, `_Wb` = W&B, `_Md` = Modal
- Local-only (most common): no suffix
- Combine: `_CWb`, `_CWbMd`

**Key rule:** writers always use timestamped/versioned paths. Readers find the latest via symlinks (`{npc}.json` → `{npc}_20260609T120000Z.json`). History is never silently overwritten.

- Config root: `etc/` (not `configs`)
- Pipeline runtime registry: `var/.pipeline/` (not `.pipeline`)
- Project state: `docs/project-state.md`
- Unified CLI: `./ucore` (real bash wrapper at root)
- Specs: `data/npcs/specs/<npc>.json`
- Reference docs: `data/npcs/reference_docs/<npc>_primer.md`
- Datasets: `data/datasets/<npc>/<technique>/`
- Clean train file: `data/datasets/<npc>/<technique>/train_clean.jsonl`
- Training runs: `artifacts/models/<npc>/runs/<run_id>/`
- Pointers: `artifacts/models/<npc>/best`, `artifacts/models/<npc>/latest`
- GGUF adapters: `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- Reports: `artifacts/eval/reports/<npc>/`
- Feedback: `artifacts/eval/results/feedback/<npc>.json`
- Unity project: `~/Setup Guide In-Editor Tutorial/`
- Unity models: `Assets/StreamingAssets/Models/`

## Current pipeline shape

```bash
# 0. preflight / process control
~/llama-servers.sh killall                              # free VRAM
./ucore audit check

# 1. spec validation
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready

# 2. generation (pick one)
# Production via Ollama:
./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
# Production via direct llama.cpp (more GPU control):
./ucore generate-local --model ~/models/qwen2.5-7b.gguf data/npcs/specs/<npc>.json --fresh
# Smoke/dev only (template):
# ./ucore generate data/npcs/specs/<npc>.json --technique template

# 3. sanitize
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

# 4. gate
./ucore dataset-eval data/npcs/specs/<npc>.json \
  --technique <technique> --mode fast --judge-model qwen2.5:7b

# 5. train/export
./ucore train data/npcs/specs/<npc>.json \
  --technique <technique> --preset fast-3b --export-gguf

# 6. evaluate adapter with base + LoRA when applicable
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

## Context hygiene

When project context looks stale:

```bash
python src/core/ops/context_audit.py
```

Then update in this order:

1. Actual repo/tool state.
2. `docs/project-state.md`.
3. `AGENTS.md`.
4. Project-local `.codex/` references, skills, and agents.
5. Project-local `.hermes/` memory/skills only when explicitly needed.
6. Global Hermes memory only for stable facts.

## Deprecated / avoid

- Deprecated inactive NPCs: `astronomy_guide`, `fitness_coach`.
- Template datasets as production data.
- **`./ucore generate --technique ollama`** — DEPRECATED. Use `generate-ollama` or `generate-local` instead.
- **Feedback loop:** NOW WORKING. `./ucore feedback --auto` uses `generate-ollama --concept-focus` + `sanitize` + `dataset-eval`. The old 1305-line non-functional feedback loop was refactored to a ~350-line working orchestrator that calls the established CLI pipeline.
- **Standalone evaluation of adapter GGUFs when base+LoRA is required.**
- `--allow-ungated-dataset` for production.
- Long historical status dumps in `AGENTS.md`.
- Root compatibility symlinks — all removed as of cleanups in June 2026. Use canonical paths only.
- Top-level `src.core.<module>` compatibility imports. Use canonical package paths instead.

## Detail docs

- `docs/project-state.md` — current canonical state.
- `docs/training-workflow.md` — detailed pipeline details.
- `docs/INDEX.md` — full documentation navigation hub with staleness map.
- `CONTRIBUTING.md` — contribution guide, PR process, agent context guidelines.
- `SETUP.md` — full dev environment setup.
- `.codex/skills/unsloth-core-pipeline-agent/SKILL.md` — Codex pipeline orchestrator and subagent router.
- `.codex/agents/ucore-pipeline-chief.agent.md` — Codex main pipeline agent prompt.
- `.hermes/README.md` — repo-local Hermes operating pack.
- `.hermes/skills/unsloth-core-context-maintenance/SKILL.md` — context cleanup workflow.
- `.hermes/skills/unsloth-core-operator/SKILL.md` — operator runbook.
- `.hermes/skills/unsloth-core-low-vram-training/SKILL.md` — 6GB VRAM training/eval survival.
- `.hermes/skills/llmunity-runtime-deploy/SKILL.md` — Unity deployment checks.
- `AGENTS.md` (this file) — project-level agent context
