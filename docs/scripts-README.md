# src/core Package Map

Last verified: 2026-06-08

The old `scripts/` compatibility path is gone. The canonical implementation tree is `src/core/`.

## Categories

- `src/core/dataset/` — dataset generation, sanitization, quality gates, spec validation
- `src/core/training/` — training loops, feedback orchestration, training support
- `src/core/evaluation/` — evaluation, comparisons, tracking, reports
- `src/core/export/` — adapter and GGUF export utilities
- `src/core/orchestration/` — planning and target execution helpers
- `src/core/ops/` — audits, smoke tests, config checks, support utilities
- `src/core/runtime/` — runtime/testing agent entrypoints and response helpers
- `src/core/tracing/` — tracing helpers and observability support

## Entry points

- CLI: `./ucore`
- Python subprocess entry for tests/tooling: `src/cli/ucore`

## Import rules

Prefer canonical imports from subpackages, for example:

```python
from src.core.dataset import sanitize_dataset
from src.core.dataset.dataset_eval import summarize_deepeval_result
from src.core.evaluation.evaluate import compare_models
from src.core.ops import smoke_test
```

Do not use removed compatibility imports such as:

```python
from src.core.dataset_eval import ...
from src.core.evaluate import ...
from src.core.smoke_test import ...
from src.core.validate_subject_spec import ...
```

## Notes

- `src/core/__init__.py` is now only a minimal package marker.
- Root-level `scripts/*.py` entrypoints are retired.
- Use `./ucore` for command execution instead of treating `src/core/` files as ad hoc standalone scripts.
