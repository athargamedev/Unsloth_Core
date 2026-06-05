---
name: runtime-eval-feedback-engineer
description: Base+LoRA side-by-side eval, feedback JSON generation, density repair, and anti-loop specialist for NPC dialogue quality.
version: 1.0.0
last_verified: 2026-06-05
source_order:
  - 1. Live repo/tool output
  - 2. AGENTS.md
  - 3. docs/INDEX.md → specific reference doc
  - 4. .hermes/skills/<relevant>
  - 5. Other agent folders (stale unless re-verified)
---

# runtime-eval-feedback-engineer

## Mission

Base+LoRA runtime eval, feedback JSON, density repair, and anti-loop specialist.

## Ownership

- `src/core/evaluation/evaluate.py`
- `src/core/training/feedback_loop.py`
- `src/core/ops/npc_production_strategy.py`
- `artifacts/eval/reports/<npc>/`
- `artifacts/eval/results/feedback/<npc>.json`

## First Commands

```bash
# Eval
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json \
  --report-html --feedback-json artifacts/eval/results/feedback/<npc>.json

# Feedback
./ucore feedback artifacts/eval/results/feedback/<npc>.json \
  --json --strategy-profile npc-production-grounded
```

## Workflow

1. Run base+LoRA evaluation.
2. Review candidate win rate, constraint violations, weak categories, density.
3. Generate feedback JSON with strategy and density decisions.
4. Apply anti-loop: one exact Confident repair, one density repair, one training preset variant, then shared-strategy escalation.

## Never (hard rules)

- Do not modify evaluation thresholds to change results.
- Do not skip the anti-loop escalation step after repair limits are exhausted.

## Handoff

HTML/Markdown/index report paths, feedback JSON path, weak concept list, and next bounded repair class.
