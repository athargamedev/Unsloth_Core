# Unsloth_Core Dataflow & Simplification Report

## 1. The `scripts/` illusion

The `scripts/` directory was a **symlink → `src/core/`** since June 1. Every file
was accessible through two paths but lived on disk once. This created the
appearance of duplication. **Removed.** All code lives in `src/core/`.

## 2. Canonical dataflow

```
validate-spec → generate-ollama → sanitize → dataset-eval → train+export → evaluate
```

| Step | CLI | Script | Status |
|---|---|---|---|
| Spec validation | `validate-spec` | `src/core/dataset/validate_subject_spec.py` | ✅ |
| Generation | `generate-ollama` | `src/core/dataset/generate_dataset.py` | ✅ qwen2.5:7b |
| Sanitize | `sanitize` | `src/core/dataset/sanitize_dataset.py` | ✅ |
| Dataset eval | `dataset-eval` | `src/core/dataset/dataset_eval.py` | ✅ DeepEval 4.0.5 |
| Training | `train` | `src/core/training/train.py` | ✅ (eval disabled for 6GB) |
| GGUF export | `--export-gguf` (train flag) | `src/core/export/export.py` + `convert_lora_to_gguf.py` | ✅ adapter-only |
| Evaluation | `evaluate` | `src/core/evaluation/evaluate.py` | ✅ needs `--base-model` |

## 3. DeepEval — is it working?

**Yes.** DeepEval 4.0.5 runs via `dataset-eval`. It:
- Judges generated dataset rows via Ollama (`qwen2.5:7b`)
- Produces `quality_summary.json` (pass rate) + `quality_failures.json` (failures)
- Is part of the canonical pipeline (step 4)
- Writes structured feedback that `generate-ollama --repair` can read

What is NOT working:
- Confident AI upload (API key scope issue — logs show warnings)
- The standalone `feedback` command (1229 lines, never proven)
- The standalone `repair` command (uses deprecated deepeval API)

## 4. Feedback loop — the real working path

The working feedback loop is **dataset-eval → generate-ollama --repair**:
1. `./ucore dataset-eval <spec>` → writes `quality_failures.json`
2. `./ucore generate-ollama <spec> --repair` → re-generates failed rows with context

The separate `./ucore feedback` and `./ucore repair` CLIs are dead code.

## 5. CLI cleanup

Commands marked `[LEGACY]`, `[DEPRECATED]`, or `[EXPERIMENTAL]` in help text:

| Command | Tag | Reason |
|---|---|---|
| `generate` | LEGACY | Use `generate-ollama` instead |
| `export-resume` | DEPRECATED | Never proven |
| `export-adapter` | DEPRECATED | `export` already does adapter-only |
| `quick-eval` | DEPRECATED | Use `evaluate` instead |
| `feedback` | DEPRECATED | Use `dataset-eval` → `generate-ollama --repair` |
| `repair` | DEPRECATED | Same path as feedback |
| `grpo-train` | EXPERIMENTAL | Not production-ready |

## 6. What to delete next (if you want to)

These scripts are untested / unreferenced by the canonical pipeline:

- `src/core/training/feedback_loop.py` (1229 lines, dead)
- `src/core/training/feedback_loop_deepeval.py` (dead API)
- `src/core/training/train_grpo_deepeval.py` (experimental)
- `src/core/export/export_resume.py` (never used)
- `src/core/export/export_adapter.py` (redundant with `export.py`)
- `src/core/evaluation/quick_eval.py` (redundant with `evaluate.py`)
- `src/core/evaluation/tb_reader.py` (developer utility)
- `src/core/evaluation/wb_report.py` (dev utility)
- `src/core/evaluation/compare_runs.py` (not in pipeline)
- `src/core/ops/compare_local_models.py` (not pipeline)
