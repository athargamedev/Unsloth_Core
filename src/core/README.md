# src/core Package Map

Last verified: 2026-06-08

This directory is the canonical home for the Python pipeline implementation.

## Categories

- `dataset/` — dataset generation, sanitization, quality gates, spec validation
- `training/` — training loops, feedback orchestration, training support
- `evaluation/` — evaluation, comparisons, tracking, reports
- `export/` — adapter and GGUF export utilities
- `orchestration/` — planning and target execution helpers
- `ops/` — audits, smoke tests, config checks, support utilities
- `runtime/` — runtime/testing agent entrypoints and response helpers
- `tracing/` — tracing helpers and observability support

## Entry points

- CLI: `./ucore`
- Python subprocess entry for tests/tooling: `src/cli/ucore`

## Import rules

Use canonical imports from subpackages.

Examples:
```python
from src.core.dataset import sanitize_dataset
from src.core.dataset.dataset_eval import summarize_deepeval_result
from src.core.evaluation.evaluate import compare_models
from src.core.ops import smoke_test
```

Do not use removed top-level compatibility aliases like `src.core.dataset_eval` or `src.core.evaluate`.

## Notes

- `src/core/__init__.py` is a minimal package marker only.
- The old `scripts/` compatibility path is retired.
- `./ucore` is the supported command surface.
