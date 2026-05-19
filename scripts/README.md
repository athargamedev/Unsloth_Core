# Scripts Directory Map

The `scripts/` folder is now organized into categories so agents can find the right area faster.

## Categories

- `scripts/dataset/` — dataset generation, sanitization, quality gates, and spec validation
- `scripts/training/` — training loops, feedback loops, and orchestration around training
- `scripts/evaluation/` — evaluation, comparison, tracking, and report generation
- `scripts/export/` — adapter and GGUF export utilities
- `scripts/orchestration/` — planning and batch execution helpers
- `scripts/ops/` — scaffolding, audits, smoke tests, config checks, and integration probes

## Entry points

Prefer importing or editing the categorized implementations under the subdirectories above.
Root-level `scripts/*.py` entrypoints have been retired; use the categorized paths or `./ucore`.
Legacy Python import aliases remain available through `scripts/__init__.py` for backward compatibility.
