# Unsloth_Core

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Agent-first pipeline for building GGUF LoRA adapters for `llama-3.2-3b-instruct`, so Unity NPCs can load adapters at runtime through LLMUnity and store dialogue/session state in local Supabase.

Current canonical state: [`docs/project-state.md`](docs/project-state.md)

---

## Contents

- [Quick Start](#quick-start)
- [North Star](#north-star)
- [Active NPCs](#active-npcs)
- [Dataset Policy](#dataset-policy)
- [Pipeline Shape](#pipeline-shape)
- [Infrastructure](#infrastructure)
- [Canonical Paths](#canonical-paths)
- [Context Hygiene](#context-hygiene)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

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
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

Dashboard:

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
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
- Production datasets must use the current approved grounded workflow. NotebookLM is no longer used.
- Quality gates must pass against the exact sanitized dataset before production training.

## Pipeline Shape

```bash
# 1. Validate
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready

# 2. Generate
# Production: current approved grounded workflow; do not use NotebookLM.
# Smoke/dev only:
./ucore generate data/npcs/specs/<npc>.json --technique template

# 3. Sanitize
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

# 4. Quality gate
./ucore dataset-eval data/npcs/specs/<npc>.json \
  --technique <technique> --mode fast --judge-model qwen2.5:7b

# 5. Train/export
./ucore train data/npcs/specs/<npc>.json \
  --technique <technique> --preset fast-3b --export-gguf

# 6. Evaluate
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
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

`src/dashboard/unity-npc-llm-training-dashboard/`

Dev:

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run dev
```

## Canonical Paths

```text
AGENTS.md                                  agent entrypoint
README.md                                  human overview
CONTRIBUTING.md                            contribution guide
SETUP.md                                   dev environment setup
docs/INDEX.md                              documentation navigation hub
docs/project-state.md                      current state
docs/training-workflow.md                  pipeline reference
ucore                                      unified CLI
data/npcs/specs/<npc>.json                 NPC specs
data/npcs/reference_docs/<npc>_primer.md   primers
data/datasets/<npc>/<technique>/           datasets
artifacts/models/<npc>/runs/<run_id>/      training runs
artifacts/models/<npc>/best                best pointer
artifacts/models/<npc>/latest              latest pointer
artifacts/exports/<npc>/<npc>-lora-f16.gguf adapter GGUF
artifacts/eval/reports/<npc>/              reports
artifacts/eval/results/feedback/<npc>.json  feedback
```

## Context Hygiene

Run stale-reference audit:

```bash
./ucore audit context
```

Do not put long historical status dumps in `AGENTS.md`. Put current facts in `docs/project-state.md`; put procedures in `.hermes/skills/`; keep memory compact.

All agent guidance files carry `last_verified` in YAML frontmatter. If you touch a file, update its date.

## Documentation

- [`AGENTS.md`](AGENTS.md) — concise agent entrypoint (T0)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute, PR process, agent context guidelines (T1)
- [`SETUP.md`](SETUP.md) — full dev environment setup (T1)
- [`docs/project-state.md`](docs/project-state.md) — current operational truth (T2)
- [`docs/training-workflow.md`](docs/training-workflow.md) — detailed training pipeline (T2)
- [`docs/INDEX.md`](docs/INDEX.md) — full documentation navigation hub
- [`.hermes/README.md`](.hermes/README.md) — repo-local Hermes operating pack

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Code style
- PR process
- How to add a new NPC
- How to run tests
- Agent context contribution guidelines

## License

MIT. See [`LICENSE`](LICENSE).
