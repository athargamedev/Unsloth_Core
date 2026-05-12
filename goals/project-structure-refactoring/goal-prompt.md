# Codex Goal Prompt: Project Structure & Workflow Refactoring

After every critical document in this folder is approved with Plannotator, paste or set this goal:

```text
/goal Transform Unsloth_Core into a professional multi-workflow training platform with structured docs, experiment tracking, TensorBoard evaluation, and a modern frontend

Use `goals/project-structure-refactoring/` as the durable source of truth:
- Read `brief.md` for the mission, context, constraints, non-goals, and ask-before rules.
- Follow `plan.md` for the solution overview (7 slices), acceptance criteria, and required evidence.
- Run the checks in `verification.md` and record evidence in `progress.jsonl`.
- Append concrete progress and proof to `progress.jsonl` — not summaries of intent.
- Pause and ask the user for anything listed in `blockers.md` or any similarly risky unresolved decision.

The 7 implementation slices are:
1. Write workflow docs: `docs/NOTEBOOKLM_WORKFLOW.md`, `docs/TEMPLATE_WORKFLOW.md`, `docs/TRAINING_WORKFLOW.md`, `docs/EVALUATION_WORKFLOW.md` (follow existing `docs/OLLAMA_WORKFLOW.md` style)
2. Move presets to YAML-only: remove PRESETS dict from train.py, load from `configs/presets/*.yaml`
3. Add experiment tracking with run IDs: `outputs/{npc_key}/runs/{run_id}/` with frozen config + symlinks
4. Professional evaluation: `scripts/compare_runs.py`, TensorBoard metrics extraction, structured reports
5. Professional frontend: upgrade dashboard to HTMX + Alpine.js + Chart.js SPA in `frontend/`
6. Standardize subject spec schema: match AGENTS.md documented fields
7. Clean up artifacts & initialize git

Key constraints:
- Prefer HTMX + Alpine.js + Chart.js for frontend (avoid heavy build toolchains)
- Never break existing trained adapters or GGUF exports
- Keep backward compatibility for all existing script invocations
- All `_config/paths.py` functions must remain functional
- Preserve config hierarchy: base YAML → preset overrides → CLI overrides

Do not mark the goal complete until every acceptance item is backed by real evidence in `progress.jsonl` and the required verification commands have passed. If any verification step fails, document the error, assess if it's a blocker, and ask the user.
```
