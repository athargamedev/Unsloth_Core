---
last_verified: 2026-06-05
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
- Current `./ucore generate` supports `docs`, `ollama`, `template`, `openai`, and `anthropic`; verify the intended production technique before training.

## Canonical pipeline

```bash
source unsloth_env/bin/activate
./ucore audit check
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
# production: generate via approved grounded path; template only for smoke
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --mode fast --judge-model qwen2.5:7b
./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf
./ucore evaluate --baseline <base-or-baseline-gguf> --candidate <adapter-or-run> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

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
| T1 Onboarding | Dev/AI setup guide | `CONTRIBUTING.md`, `SETUP.md` [planned] |
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

**Next phases (planned):**
- Create standard agent brief template
- Create CONTRIBUTING.md, SETUP.md, proper README.md
- Deduplicate split skills (`.hermes` vs `.codex` context-maintenance)
- Extend `context_audit.py` for automated freshness scanning
- Walk through SETUP.md from fresh clone
