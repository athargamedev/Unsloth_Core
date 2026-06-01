# Unsloth_Core

Agent-first pipeline for building GGUF LoRA adapters for `llama-3.2-3b-instruct`, so Unity NPCs can load adapters at runtime through LLMUnity and store dialogue/session state in local Supabase.

Current canonical state: `docs/PROJECT_STATE.md`

## North Star

- Train and export high-quality LoRA adapters as GGUF.
- Load one shared base GGUF in Unity/LLMUnity and swap lightweight LoRA adapters per NPC.
- Keep dataset generation, quality gates, training, export, and evaluation aligned to Unity runtime behavior.

## Quick Start

```bash
# Python environment
source unsloth_env/bin/activate

# Health check
./ucore audit check

# Validate active NPC specs
./ucore validate-spec subjects/NPC_specs/history_guide.json --generation-ready
./ucore validate-spec subjects/NPC_specs/chef_assistant.json --generation-ready
```

Dashboard:

```bash
cd frontend_control/unity-npc-llm-training-dashboard
npm run dev
```

Dashboard runs on port `3100`.

## Active NPCs

Only these are active for prototype validation:

| NPC | Key | Subject | State |
|-----|-----|---------|-------|
| History Guide | `history_guide` | World history | Active |
| Chef Assistant | `chef_assistant` | Culinary arts | Active |

Deprecated as active context unless explicitly reactivated: `astronomy_guide`, `fitness_coach`, and any other older prototype NPCs.

## Dataset Policy

- Template generation is smoke/dev only.
- Never train production LoRA on template data.
- Production datasets must use NotebookLM CLI / approved grounded workflow.
- Quality gates must pass against the exact sanitized dataset before production training.

## Pipeline Shape

```bash
# 1. Validate
./ucore validate-spec subjects/NPC_specs/<npc>.json --generation-ready

# 2. Generate
# Production: NotebookLM CLI / approved grounded workflow.
# Smoke/dev only:
./ucore generate subjects/NPC_specs/<npc>.json --technique template

# 3. Sanitize
./ucore sanitize subjects/datasets/<npc>/<technique>/train.jsonl \
  --output subjects/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

# 4. Quality gate
./ucore dataset-eval subjects/NPC_specs/<npc>.json \
  --technique <technique> --mode fast --judge-model qwen2.5:7b

# 5. Train/export
./ucore train subjects/NPC_specs/<npc>.json \
  --technique <technique> --preset fast-3b --export-gguf

# 6. Evaluate
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec subjects/NPC_specs/<npc>.json --report-html
```

## Infrastructure

### Supabase

Local Supabase:

- DB: `15434`
- API/Kong: `16437`
- Studio: `16438`

Start:

```bash
supabase start
```

### Dashboard

Package path:

`frontend_control/unity-npc-llm-training-dashboard/`

Dev:

```bash
cd frontend_control/unity-npc-llm-training-dashboard
npm run dev
```

## Canonical Paths

```text
AGENTS.md                                  agent entrypoint
README.md                                  human overview
docs/PROJECT_STATE.md                      current state
ucore                                      unified CLI
subjects/NPC_specs/<npc>.json              NPC specs
subjects/reference_docs/<npc>_primer.md    primers
subjects/datasets/<npc>/<technique>/        datasets
outputs/<npc>/runs/<run_id>/                training runs
outputs/<npc>/best                          best pointer
outputs/<npc>/latest                        latest pointer
exports/<npc>/<npc>-lora-f16.gguf           adapter GGUF
eval/reports/<npc>/                         reports
eval/results/feedback/<npc>.json            feedback
```

## Context Hygiene

Run stale-reference audit:

```bash
python scripts/ops/context_audit.py
```

Do not put long historical status dumps in `AGENTS.md`. Put current facts in `docs/PROJECT_STATE.md`; put procedures in `.hermes/skills/`; keep memory compact.

## Documentation

- `AGENTS.md` — concise agent entrypoint
- `docs/PROJECT_STATE.md` — current operational truth
- `docs/TRAINING_WORKFLOW_CONTEXT.md` — detailed training pipeline
- `.hermes/README.md` — repo-local Hermes operating pack

## License

MIT. See `LICENSE`.
