# scripts/ AGENTS

## Purpose
This folder contains the repo's runnable pipeline scripts, organized by category.

## Rules
- Prefer the categorized implementation files under `scripts/dataset/`, `scripts/training/`, `scripts/evaluation/`, `scripts/export/`, `scripts/orchestration/`, and `scripts/ops/`.
- Do not add new root-level `scripts/*.py` entrypoints; place implementations directly in the appropriate category.
- Use `_repo_root.py` for repo-root resolution in categorized modules.
- Preserve `./ucore` behavior and update docs or callers whenever a command path changes.
- If a script touches output paths, resolve them through `_config/paths.py`.
- Always add or update regression tests for path/layout behavior.

## Quick checks
- `python -m py_compile scripts/**/*.py`
- `pytest -q tests/test_pipeline_boundaries.py`
- `./ucore audit check`
