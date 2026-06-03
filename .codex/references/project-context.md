# Unsloth_Core Codex Context

Use this when work touches the NPC pipeline, dashboard, Unity deployment, local training, or repo context maintenance.

## Precedence

1. Live repo/tool output.
2. `AGENTS.md`.
3. `.codex/references/*`.
4. `docs/project-state.md` and `docs/training-workflow.md`.
5. `.hermes/*` and `.agents/*` as migration/reference material only.
6. Global memory, only after verification when facts may have drifted.

Known drift: `AGENTS.md` says NotebookLM is no longer used for production. `docs/project-state.md` still mentions NotebookLM from 2026-06-01. Until the user changes this, follow `AGENTS.md`: production uses the current approved grounded workflow, and template generation is smoke/dev only.

## Active Scope

- Active NPCs: `history_guide`, `chef_assistant`.
- Inactive/deprecated unless user reactivates: `astronomy_guide`, `fitness_coach`, `marvel_heroes_instructor`.
- Local judge/default for low-cost checks: `qwen2.5:7b`.
- Production strategy profile: `npc-production-grounded`.
- Local GPU: RTX 3060-class 6 GB VRAM. Check and unload Ollama before train/eval if it holds VRAM.

## Hard Rules

- Do not train production LoRA on template data.
- Do not lower eval thresholds, dataset minimums, or runtime constraints to force a pass.
- Treat `quality_failures.json` as repair input.
- Evaluate adapter GGUFs with the required base model; do not treat adapter GGUFs as standalone full models.
- Keep durable context compact. Procedures belong in skills, not long status dumps.
- Use final reporting shape: `Done`, `Changed`, `Ran`, `Result`, `Blocked`, `Next`.

## Canonical Paths

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
- Dashboard: `src/dashboard/unity-npc-llm-training-dashboard/`
- Unity project: `/home/athar/Setup Guide In-Editor Tutorial/`
- Unity models: `Assets/StreamingAssets/Models/`
- Local Supabase ports: DB `15434`, API/Kong `16437`, Studio `16438`.

## Strategy Facts

`./ucore strategy --profile npc-production-grounded` currently reports:

- Technique: `ollama`.
- Dataset target: 120.
- Quality gate: release / wandb / cases=3.
- Training: `fast-3b`, r16, alpha32, seq=512.
- Runtime eval: base model required, HTML report enabled.
- Anti-loop limits: one exact Confident repair, one density repair, one training preset variant per NPC before shared-strategy escalation.

