# Unsloth_Core: Agent Context

Primary source of truth for agents in this repo. Keep this file short and current. Detailed state lives in `docs/project-state.md`; full workflow docs live in `docs/training-workflow.md`.

## Mission

Build high-quality GGUF LoRA adapters for llama3.2 3B NPCs. Unity/LLMUnity loads one shared base GGUF and swaps lightweight LoRA adapter GGUFs plus NPC system prompts. Local Supabase stores dialogue/session state.

## Active project state

- Active NPCs: `history_guide`, `chef_assistant` only.
- Production dataset rule: use NotebookLM CLI / approved grounded workflow. Template generation is smoke/dev only.
- Local tested Ollama judge/default: `qwen2.5:7b` unless a fresh benchmark says otherwise.
- Local GPU: RTX 3060-class 6GB VRAM. Unload Ollama before train/eval when it holds VRAM.
- Dashboard app lives in `src/dashboard/unity-npc-llm-training-dashboard/`.
- Supabase local ports: DB `15434`, API/Kong `16437`, Studio `16438`.

## Hard rules

- Do not train production LoRA on template data.
- Do not mark inactive NPCs as active unless the user reactivates them.
- Do not lower eval thresholds, dataset minimums, or runtime constraints to force a pass.
- Treat `quality_failures.json` as repair input, not something to delete.
- Verify actual repo/tool state before updating docs or memories.
- Keep durable memory compact. Procedures belong in skills.
- Use caveman reporting: Done/Changed/Ran/Result/Blocked/Next.

## Quick start

```bash
source unsloth_env/bin/activate
./ucore audit check
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

Dashboard:

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run dev
```

## Canonical paths

- Project state: `docs/project-state.md`
- Unified CLI: `./ucore`
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
# 1. preflight / health
./ucore audit check

# 2. spec validation
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready

# 3. generation
# Production: NotebookLM CLI / approved grounded workflow.
# Smoke only:
./ucore generate data/npcs/specs/<npc>.json --technique template

# 4. sanitize
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

# 5. gate
./ucore dataset-eval data/npcs/specs/<npc>.json \
  --technique <technique> --mode fast --judge-model qwen2.5:7b

# 6. train/export
./ucore train data/npcs/specs/<npc>.json \
  --technique <technique> --preset fast-3b --export-gguf

# 7. evaluate adapter with base + LoRA when applicable
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
4. Project-local `.hermes/` memory/skills.
5. Global Hermes memory only for stable facts.

## Deprecated / avoid

- Deprecated inactive NPCs: `astronomy_guide`, `fitness_coach`.
- Template datasets as production data.
- Deprecated judge refs: do not use `qwen3:latest` as confirmed local default without re-verification.
- Standalone evaluation of adapter GGUFs when base+LoRA is required.
- `--allow-ungated-dataset` for production.
- Long historical status dumps in `AGENTS.md`.

## Detailed docs

- `docs/project-state.md` — current canonical state.
- `docs/training-workflow.md` — full pipeline details.
- `.hermes/README.md` — repo-local Hermes operating pack.
- `.hermes/skills/unsloth-core-context-maintenance/SKILL.md` — context cleanup workflow.
- `.hermes/skills/unsloth-core-operator/SKILL.md` — operator runbook.
- `.hermes/skills/unsloth-core-low-vram-training/SKILL.md` — 6GB VRAM training/eval survival.
- `.hermes/skills/llmunity-runtime-deploy/SKILL.md` — Unity deployment checks.
