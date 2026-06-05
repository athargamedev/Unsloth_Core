---
name: unsloth-core-operator
description: "Use when operating, debugging, or changing Unsloth_Core NPC workflows: specs, generation, sanitize, dataset-eval, train, export, evaluate, feedback, strategy, artifact paths, or Unity LoRA readiness."
last_verified: 2026-06-05
---

# Unsloth_Core Operator

Use `AGENTS.md` first. Then read `.codex/references/project-context.md` and `.codex/references/current-commands.md` when commands or paths matter.

If `.hermes`, `.agents`, or older docs conflict with `AGENTS.md`, verify current repo/tool output and follow the newer verified source.

## Report Format

Use:

```text
Done: ...
Changed: ...
Ran: ...
Result: ...
Blocked: ...
Next: ...
```

## First Checks

```bash
git status --short
./ucore audit check
./ucore strategy --profile npc-production-grounded
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

Use `./ucore --watch <subcommand> ...` for long/noisy commands so logs land under `/tmp/ucore-watch/`.

## Non-Negotiables

- Active NPCs: `history_guide`, `chef_assistant`.
- Production technique from `npc-production-grounded`: `ollama`.
- Template generation is smoke/dev only.
- Do not lower thresholds or dataset minimums to pass.
- Treat `quality_failures.json` as repair input.
- Evaluate LoRA adapter GGUFs with the required base GGUF.
- Use repo path helpers and existing CLI surfaces before inventing paths.

## Pipeline Shape

```bash
./ucore generate data/npcs/specs/<npc>.json --technique ollama
./ucore sanitize data/datasets/<npc>/ollama/train.jsonl \
  --output data/datasets/<npc>/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json --technique ollama --mode fast --judge-model qwen2.5:7b
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json --technique ollama --preset fast-3b --export-gguf
./ucore evaluate --baseline <baseline> --candidate <candidate> --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

## Anti-Loop

Use `./ucore feedback --json --strategy-profile npc-production-grounded` when deciding next repair. Respect `strategy_decision` and `density_decision`:

- one exact Confident failure repair
- one density repair
- one training preset variant
- then escalate to shared strategy/preset instead of another per-NPC loop

## Validation

For narrow changes, run focused tests. For shared contracts, run:

```bash
pytest -q tests/test_workflow_coherence_contract.py
pytest -q tests -m 'not live_model and not requires_ollama and not requires_gpu and not requires_supabase'
```
