# scripts/ AGENTS

## Purpose
This folder contains the repo's runnable pipeline scripts and thin compatibility wrappers.

## Rules
- Prefer the categorized implementation files under `scripts/dataset/`, `scripts/training/`, `scripts/evaluation/`, `scripts/export/`, `scripts/orchestration/`, and `scripts/ops/`.
- Keep root-level `scripts/*.py` files as wrappers only.
- When adding a new script, place the implementation in the appropriate category first, then add a wrapper only if backward compatibility is needed.
- Use `_repo_root.py` for repo-root resolution in categorized modules.
- Preserve `./ucore` behavior and avoid changing command paths without updating wrappers and docs.
- If a script touches output paths, resolve them through `_config/paths.py`.
- Always add or update regression tests for path/layout behavior.

## Quick checks
- `python -m py_compile scripts/**/*.py`
- `pytest -q tests/test_pipeline_boundaries.py`
- `./ucore audit check`
