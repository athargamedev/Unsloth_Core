# src/core/ AGENTS

## Purpose
This folder contains the repo's pipeline implementation, organized by concern.

## Rules
- Prefer canonical imports from `src.config.paths` for path resolution.
- Do not add new root-level `scripts/*.py` entrypoints; place implementations in the appropriate category under `src/core/`.
- Preserve `./ucore` behavior and update docs or callers whenever a command path changes.
- Always add or update regression tests for path/layout behavior.

## Quick checks
- `python -m py_compile src/core/**/*.py src/config/**/*.py`
- `pytest -q tests/test_pipeline_boundaries.py`
- `./ucore audit check`
