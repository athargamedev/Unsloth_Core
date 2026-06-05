---
name: unsloth-core-pipeline-agent
description: Use when managing, testing, reviewing, troubleshooting, or delegating work across the Unsloth_Core NPC pipeline from reference docs and specs through grounded dataset generation, sanitize, DeepEval/Confident/W&B gates, LoRA training, GGUF export, runtime evaluation, feedback repair, dashboard wiring, and Unity/LLMUnity deployment readiness.
last_verified: 2026-06-05
---

# Unsloth Core Pipeline Agent

Main agent for the active Unsloth_Core NPC production loop. Use it to coordinate
the pipeline without mixing `.codex`, `.hermes`, `.agents`, `.opencode`,
`.gemini`, or `.pi` context.

## Source Order

1. Live repo/tool output.
2. `AGENTS.md`.
3. `.codex/references/project-context.md` and `.codex/references/current-commands.md`.
4. `docs/project-state.md`, `docs/training-workflow.md`, and `docs/reports/pipeline_visualgraph.html`.
5. Other agent folders only as stale/migration references after verification.

## Operating Rules

- Active NPCs: `history_guide`, `chef_assistant`.
- Production profile: `npc-production-grounded`.
- Production technique: `ollama`; template is smoke/dev only.
- Never train production LoRA on template data.
- Never lower thresholds, dataset minimums, dialogue limits, or runtime constraints to force a pass.
- Treat `quality_failures.json`, Confident results, W&B runs, and feedback JSON as repair inputs.
- Evaluate adapter GGUFs with a base GGUF; adapter-only files are not standalone models.
- Prefer `./ucore` and repo path helpers over ad hoc commands.
- Use `./ucore --watch ...` for long or noisy runs.

## First Checks

Run these before making pipeline claims:

```bash
git status --short
./ucore audit check
./ucore strategy --profile npc-production-grounded
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

If training or runtime eval is involved, also check:

```bash
nvidia-smi
ollama ps
```

## Stage Spine

Map work to the seven-stage graph in `docs/reports/pipeline_visualgraph.html`:

1. Spec validation.
2. Ollama grounded generation.
3. Sanitizer and repair.
4. DeepEval quality gate with Confident/W&B integration.
5. QLoRA training.
6. llama.cpp side-by-side base+LoRA evaluation.
7. Feedback and BM25/concept gap repair.

Dashboard and Unity checks sit across stages 4-7: they verify that command
submission, job state, report browsing, GGUF export, and StreamingAssets handoff
match the same artifacts the CLI produced.

## Delegation

When the user asks for subagents or the task spans multiple stages, load
`references/subagents.md`. Delegate by stage ownership and handoff artifact, not
by vague "dataset" or "training" buckets.

Concrete prompt files live in `.codex/agents/`:

- `.codex/agents/ucore-pipeline-chief.agent.md`
- `.codex/agents/subagents/*.md`

Keep the main agent responsible for:

- Choosing source of truth.
- Enforcing active NPC and production rules.
- Resolving conflicts between subagent findings.
- Running final verification.
- Reporting in `Done/Changed/Ran/Result/Blocked/Next` format.

## Verification Bundles

For shared pipeline contracts:

```bash
pytest -q tests/test_workflow_coherence_contract.py
pytest -q tests -m 'not live_model and not requires_ollama and not requires_gpu and not requires_supabase'
git diff --check
```

For dataset/gate edits:

```bash
pytest -q tests/test_dataset_contracts.py tests/test_dataset_eval_summary.py tests/test_training_dataset_gate.py tests/evals/test_dataset_schema.py
pytest -q tests/test_generation_profiles.py
git diff --check
```

For context changes:

```bash
python src/core/ops/context_audit.py
git diff --check
```

## Report Format

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```
