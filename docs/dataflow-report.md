# Unsloth_Core Dataflow & Simplification Report

> **⚠️ HISTORICAL DOCUMENT.** This was written during the June 2026 project cleanup.
> The simplification described here has been completed. For current pipeline details,
> see [`docs/training-workflow.md`](training-workflow.md), [`docs/project-state.md`](project-state.md),
> and [`docs/INDEX.md`](INDEX.md).
>
> Last verified: 2026-06-10 (historical record, no further updates expected)

## 1. The old `scripts/` illusion

The old `scripts/` path was a compatibility symlink to `src/core/`. It has been removed.
All pipeline code now lives only in `src/core/`.

## 2. Canonical dataflow

```text
validate-spec → generate-ollama → sanitize → dataset-eval → train+export → evaluate
```

| Step | CLI | Script | Status |
|---|---|---|---|
| Spec validation | `validate-spec` | `src/core/dataset/validate_subject_spec.py` | active |
| Generation | `generate-ollama` | `src/core/dataset/generate_dataset.py` | active |
| Sanitize | `sanitize` | `src/core/dataset/sanitize_dataset.py` | active |
| Dataset eval | `dataset-eval` | `src/core/dataset/dataset_eval.py` | active |
| Training | `train` | `src/core/training/train.py` | active |
| GGUF export | `train --export-gguf` or `export` | `src/core/export/` | active |
| Evaluation | `evaluate` | `src/core/evaluation/evaluate.py` | active |

## 3. Feedback loop

The feedback loop is no longer dead code.

Current working path:
1. `./ucore feedback --auto` or `./ucore feedback --json`
2. Internally orchestrates maintained CLI stages:
   - `generate-ollama --concept-focus ...`
   - `sanitize`
   - `dataset-eval`
   - optional retrain path

The old broken monolith was replaced by a working orchestrator in `src/core/training/feedback_loop.py`.

## 4. Import surface simplification

Retired:
- top-level `src.core` compatibility aliases like `src.core.dataset_eval` and `src.core.evaluate`
- Python-via-wrapper usage like `python ./ucore`

Current rule:
- use canonical imports from subpackages only
- use `./ucore` for shell execution
- use `src/cli/ucore` for Python subprocess tests/tooling

## 5. What was actually removed

- orphan `src/core` files with no importers/tests/CLI route
- dead CLI routes tied to those orphan files
- test-only production shims added during stabilization
- final `src/core/__init__.py` lazy alias shim

## 6. Current simplification state

- `src/core` Python files: 85 total
- non-`__init__` Python files: 74
- canonical CLI commands: 30 top-level commands
- active production NPCs: `history_guide`, `chef_assistant`, `marvel_heroes_instructor`

## 7. Remaining simplification targets

- stale `subjects/` path references still left in source/docs
- train-gate lineage hardening
- live eval timeout/runtime cleanup for DeepEval/Ollama-heavy suites
- eventual deeper cleanup of optional/legacy modules that are still intentionally kept
