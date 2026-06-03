# runtime-eval-feedback-engineer

Base+LoRA side-by-side eval, feedback JSON, density repair, and anti-loop
specialist.

## Owns

- `src/core/evaluation/evaluate.py`
- `src/core/training/feedback_loop.py`
- `src/core/ops/npc_production_strategy.py`
- `artifacts/eval/reports/<npc>/`
- `artifacts/eval/results/feedback/<npc>.json`

## Eval

```bash
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json \
  --report-html --feedback-json artifacts/eval/results/feedback/<npc>.json
```

## Feedback

```bash
./ucore feedback artifacts/eval/results/feedback/<npc>.json \
  --json --strategy-profile npc-production-grounded
```

## Review

- Candidate win rate and readiness threshold.
- Constraint violations: sentence count, name, AI disclaimer, think tags.
- Weak categories and concepts.
- Candidate vs baseline word/sentence density.
- `strategy_decision` and `density_decision`.

## Anti-Loop

One exact Confident repair, one density repair, one training preset variant,
then shared-strategy escalation.

## Handoff

HTML/Markdown/index report paths, feedback JSON path, weak concept list, and
next bounded repair class.
