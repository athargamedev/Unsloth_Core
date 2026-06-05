# Unsloth_Core Commands & Flags Dictionary

> **Exhaustive reference** of every CLI command, subcommand, flag, config key, preset,
> contract constant, and parameter across the entire Unsloth_Core pipeline.
>
> Generated from: `ucore` (1040 lines), 7 preset YAMLs, 4 config YAMLs,
> 6 Python source files.

---

## Table of Contents

1. [CLI Commands (ucore subcommands)](#1-cli-commands-ucore-subcommands)
2. [Dataset Categories & Contract Constants](#2-dataset-categories--contract-constants)
3. [Generation Techniques](#3-generation-techniques)
4. [Ollama Model Presets](#4-ollama-model-presets)
5. [Training Presets](#5-training-presets)
6. [Training Parameters (from base YAML)](#6-training-parameters-from-base-yaml)
7. [Sanitize Settings](#7-sanitize-settings)
8. [Dataset Eval (DeepEval) Settings](#8-dataset-eval-deepeval-settings)
9. [Evaluation Settings (./ucore evaluate)](#9-evaluation-settings-ucore-evaluate)
10. [Feedback Loop Settings](#10-feedback-loop-settings)
11. [Preflight / Preheat Settings](#11-preflight--preheat-settings)
12. [Model Size → Preset Mapping](#12-model-size--preset-mapping)
13. [Workload Policy](#13-workload-policy)
14. [Promotion Rules](#14-promotion-rules)
15. [Export Settings](#15-export-settings)
16. [Engine / Inference Settings](#16-engine--inference-settings)
17. [W&B Settings](#17-wb-settings)
18. [CLI Global Flags](#18-cli-global-flags)
19. [Spec Validation Checks](#19-spec-validation-checks)
20. [Environment Variables](#20-environment-variables)

---

## 1. CLI Commands (ucore subcommands)

Every subcommand registered on the `ucore` argparse root parser.

### Global Flags (apply to every subcommand)

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--workflow-hooks PATH` | `str` | `None` | Path to a JSONL hook log for step tracing (injected into `WORKFLOW_HOOKS_PATH` env) |
| `--watch` | `bool` | `False` | Stream command output with early error alerts and save a watch log (`UCORE_WATCH=1`) |

---

### `generate`
Generate dataset from a subject spec.

| Flag | Type | Default | Choices |
|------|------|---------|---------|
| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
| `--ollama` | `bool` | `False` | Shortcut for `--technique ollama` |
| `--technique` | `str` | `template` | `docs`, `ollama`, `template`, `openai`, `anthropic` |
| `--docs-manifest PATH` | `str` | — | Docs corpus manifest override for `--technique docs` |
| `--model MODEL` | `str` | — | LLM model name for ollama/openai/anthropic |
| `--concept-focus CAT` | `str[]` | — | Focus on specific categories (repeatable, boosts example count) |
| `--fresh` | `bool` | `False` | Ignore checkpoint recovery, regenerate from scratch |
| `--push-to-confident` | `bool` | `False` | Push generated dataset to Confident AI with alias `npc-dataset-{npc_key}-{technique}` |

---

### `generate-ollama`
Generate dataset using optimized Ollama generator (defaults to local `llama3.1-3060-chat`).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
| `--model MODEL` | `str` | `llama3.1-3060-chat:latest` | Ollama model |
| `--url URL` | `str` | `http://localhost:11434` | Ollama server URL |
| `--batch-size N` | `int` | `4` | Concurrent generation tasks |
| `--max-retries N` | `int` | `3` | Max retries per generation |
| `--temperature T` | `float` | `0.6` | Generation temperature |
| `--multi-turn-ratio T` | `float` | `0.25` | Fraction of rows to request as two-turn dialogues |
| `--seed N` | `int` | `42` | Random seed |
| `--output`, `-o PATH` | `str` | — | Output JSONL path |
| `--no-validation` | `bool` | `False` | Skip validation split |
| `--val-split T` | `float` | `0.12` | Validation split ratio |
| `--check-health` | `bool` | `False` | Verify Ollama is running |
| `--pull-model` | `bool` | `False` | Auto-pull model if not found |
| `--concept-focus CAT` | `str[]` | — | Focus regeneration on specific categories (repeatable) |
| `--dry-run` | `bool` | `False` | Show plan without generating |
| `--fresh` | `bool` | `False` | Ignore checkpoint recovery |

---

### `sanitize`
Sanitize a generated dataset (remove AI artifacts, fix formatting).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `input` (positional) | `str` | *required* | Path to input JSONL |
| `--output`, `-o PATH` | `str` | `*_clean.jsonl` | Path to output JSONL |
| `--min-length N` | `int` | `10` | Min chars for assistant response |
| `--max-sentences N` | `int` | `5` | Max sentences for assistant response |
| `--verbose`, `-v` | `bool` | `False` | Print discarded examples and metadata warnings |
| `--spec PATH` | `str` | — | Path to NPC spec JSON (better quality scoring) |
| `--strict-canonical` | `bool` | `False` | Require canonical dataset path |
| `--strict-mode` | `bool` | `False` | Raise on structural validation errors instead of discarding |
| `--artifact-check` | `str` | `strict` | `strict`, `warn`, `off` |
| `--verbose-artifacts` | `bool` | `False` | Show exact artifact pattern matched |
| `--quality-threshold-pass N` | `int` | `70` | Minimum total score to pass |
| `--quality-threshold-flag N` | `int` | `50` | Below this total, examples flagged for review |
| `--quality-report` | `bool` | `False` | Print quality score distribution at end |
| `--discard-below-score N` | `int` | `0` | Discard examples below this total score (0 = keep all) |
| `--no-fix-metadata` | `bool` | `False` | Disable auto-repair of missing metadata fields |
| `--require-complete-metadata` | `bool` | `False` | Error out if any metadata field is missing |
| `--dedup` / `--no-dedup` | `bool` | `True` | Enable/disable content_hash deduplication |
| `--dedup-report` | `bool` | `False` | Show which content hashes removed during dedup |
| `--write-manifest` / `--no-write-manifest` | `bool` | `True` | Enable/disable enriched manifest writing |
| `--manifest-path PATH` | `str` | — | Override manifest output path |
| `--debug` | `bool` | `False` | Re-raise exceptions with traceback for debugging |

---

### `dataset-eval`
Run DeepEval quality checks on a generated dataset (quality gate).

| Flag | Type | Default | Choices |
|------|------|---------|---------|
| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
| `--technique TECH` | `str` | `template` | `docs`, `ollama`, `template`, `openai`, `anthropic` |
| `--judge-model MODEL` | `str` | *auto (presets)* | Local Ollama judge model |
| `--judge-preset PRESET` | `str` | *auto (presets)* | `judge-qwen25`, `judge-llama31-exp`, `judge-qwen35-exp`, `judge-qwen3-exp` |
| `--ollama-base-url URL` | `str` | `http://localhost:11434` | Ollama server URL |
| `--judge-temperature T` | `float` | `0.0` | Judge temperature |
| `--mode` | `str` | `fast` | `fast`, `release` |
| `--cases-per-category N` | `int` | *mode-dependent* | Rows sampled per category (1 for fast, 5 for release) |
| `--categories CATS` | `str` | — | Comma-separated category filter |
| `--identifier ID` | `str` | — | DeepEval run identifier |
| `--display` | `str` | `all` | `all`, `failing`, `passing` |
| `--ignore-errors` | `bool` | `False` | Continue when individual metric calls error |
| `--soft-fail` | `bool` | `False` | Write artifacts but return 0 even when metrics fail |
| `--output PATH` | `str` | — | Quality summary JSON path |
| `--wandb` | `bool` | `False` | Enable W&B logging |
| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
| `--confident` | `bool` | `False` | Enforce that CONFIDENT_API_KEY is configured (exits with error if missing) |

---

### `train`
Train a model (LoRA SFT).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `config_or_spec` (pos.) | `str` | *required* | Path to config YAML or subject spec |
| `--from-spec` | `bool` | `False` | Train directly from spec (auto when suffix is `.json`) |
| `--preset PRESET` | `str` | — | Training preset |
| `--technique TECH` | `str` | — | `docs`, `ollama`, `template`, `openai`, `anthropic` |
| `--model MODEL` | `str` | — | Base model ID/path override |
| `--export-gguf` | `bool` | `False` | Export to GGUF after training (adapter mode for Unity) |
| `--full-merge-export` | `bool` | `False` | Full merge export after training (slower, standalone GGUF) |
| `--wandb` | `bool` | *from config* | Enable W&B logging (overrides config) |
| `--no-wandb` | `bool` | — | Disable W&B logging (overrides config) |
| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
| `--lr T` | `float` | — | Learning rate |
| `--batch-size N` | `int` | — | Batch size |
| `--epochs N` | `int` | — | Number of epochs |
| `--lora-r N` | `int` | — | LoRA rank |
| `--lora-alpha N` | `int` | — | LoRA alpha |
| `--lr-scheduler SCHED` | `str` | — | Learning rate scheduler type |
| `--allow-ungated-dataset` | `bool` | `False` | Train without a fresh passing dataset-eval artifact |

---

### `smoke`
Smoke test a GGUF model.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `model` (positional) | `str` | *required* | Path to GGUF model |
| `--spec PATH` | `str` | — | Path to subject spec for context |
| `--check-integrity` | `bool` | `False` | Validate GGUF file structure (no inference) |
| `--track` | `bool` | `False` | Track results in Supabase |

---

### `validate-config`
Resolve and validate effective training config.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec PATH` | `str` | — | Path to subject spec JSON |
| `--config PATH` | `str` | — | Path to YAML config |
| `--preset PRESET` | `str` | — | Training preset |
| `--data PATH` | `str` | — | Training data path |
| `--model MODEL` | `str` | — | Model ID override |
| `--output PATH` | `str` | — | Output dir override |
| `--npc-key KEY` | `str` | — | NPC key when using `--config` |
| `--format` | `str` | `yaml` | `yaml`, `json` |
| `--strict` | `bool` | `False` | Treat warnings as errors |
| `--require-canonical` | `bool` | `False` | Require canonical dataset train path |

---

### `validate-spec`
Validate subject specs before generation/training.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `spec` (positional, optional) | `str` | — | Path to subject spec JSON |
| `--all` | `bool` | `False` | Validate every `data/npcs/specs/*.json` spec |
| `--json` | `bool` | `False` | Output JSON |
| `--strict` | `bool` | `False` | Treat warnings as errors |
| `--require-reference-docs` | `bool` | `False` | Fail if `reference_doc` missing/unreadable |
| `--require-reference-contract` | `bool` | `False` | Fail unless `reference_doc` meets generation-readiness minimums |
| `--require-all-categories` | `bool` | `False` | Fail unless all 5 dataset categories have positive counts |
| `--require-dataset-minimums` | `bool` | `False` | Fail unless all categories meet minimum SFT counts |
| `--generation-ready` | `bool` | `False` | Fail unless spec is ready for fresh dataset generation |

---

### `export`
Export trained LoRA adapter to GGUF (adapter-only by default).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `npc_key` (positional) | `str` | *required* | NPC key (snake_case) |
| `--model`, `-m MODEL` | `str` | *auto-detected* | Base model ID |
| `--quantization TYPE` | `str` | `q4_k_m` | GGUF quantization for full-merge mode |
| `--full-merge` | `bool` | `False` | Produce full merged GGUF (slower, standalone) |
| `--skip-f16` | `bool` | `False` | In full-merge mode: skip f16 variant |
| `--outtype TYPE` | `str` | `f16` | `f32`, `f16`, `bf16`, `q8_0` |
| `--maximum-memory GB` | `float` | — | Max memory (GB) for `save_pretrained_gguf` (full-merge) |
| `--resume` | `bool` | `False` | Skip GGUFs that already exist |

---

### `export-resume`
Resume/continue GGUF export for an NPC.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `npc_key` (positional) | `str` | *required* | NPC key |
| `--model`, `-m MODEL` | `str` | — | Base model ID |
| `--quantization TYPE` | `str` | `q4_k_m` | GGUF quantization |
| `--skip-f16` | `bool` | `False` | Skip exporting f16 variant |
| `--timeout-seconds N` | `int` | `5400` | Per-variant timeout |

---

### `export-adapter`
Export LoRA adapter as GGUF (for LLMUnity).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `adapter_path` (pos., optional) | `str` | — | Path to PEFT adapter directory |
| `--all`, `-a` | `bool` | `False` | Convert all adapters in `outputs/` |
| `--outtype TYPE` | `str` | `f16` | `f32`, `f16`, `bf16`, `q8_0`, `auto` |
| `--outfile PATH` | `str` | — | Explicit output file path |

---

### `deploy`
Deploy exports to Unity project.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--unity-project`, `-u PATH` | `str` | *auto-detected* | Path to Unity project |
| `--dry-run` | `bool` | `False` | Show what would be done without copying |
| `--skip-export` | `bool` | `False` | Skip GGUF export step |
| `--export-only` | `bool` | `False` | Only export, skip Unity copy |

---

### `evaluate`
Compare two GGUF models side-by-side with optional LLM judge.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--baseline PATH` | `str` | — | Baseline GGUF model path |
| `--candidate PATH` | `str` | — | Candidate GGUF model path |
| `--model`, `-m PATH` | `str` | — | Single model GGUF path (interactive) |
| `--spec`, `-s PATH` | `str` | — | Subject spec JSON |
| `--val-data PATH` | `str` | — | Validation JSONL path |
| `--num-questions N` | `int` | `10` | Number of eval questions |
| `--output`, `-o PATH` | `str` | — | Output report path |
| `--report-html` | `bool` | `False` | Generate HTML report with charts |
| `--judge` | `bool` | `False` | Use local Ollama judge |
| `--judge-model MODEL` | `str` | `llama3.1:latest` | Judge model |
| `--track` | `bool` | `False` | Track results in `eval/results/` |
| `--wandb` | `bool` | `False` | Enable W&B evaluation tracking |
| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
| `--interactive`, `-i` | `bool` | `False` | Interactive chat mode |
| `--port N` | `int` | `8888` | llama-server port |
| `--gpu-layers N` | `int` | `99` | GPU layers to offload (0 = CPU-only) |
| `--max-tokens N` | `int` | `256` | Max generated tokens per eval answer |
| `--feedback-json PATH` | `str` | — | Save structured per-concept eval results for feedback loop |
| `--base-model PATH` | `str` | — | Base GGUF path (required when `--candidate` is a LoRA adapter) |
| `--lora-weight T` | `float` | `1.0` | LoRA adapter weight |
| `--host ADDR` | `str` | `127.0.0.1` | llama-server host |
| `--training-metrics [PATH]` | `str` | — | Show training metrics from TensorBoard logs (optional: runs dir) |
| `--npc-key KEY` | `str` | — | NPC key for per-model TensorBoard runs lookup |
| `--deepeval` | `bool` | `False` | Run DeepEval model quality evaluation after conventional eval |
| `--deepeval-judge-model` | `str` | `qwen3:latest` | Ollama model to use as judge |
| `--deepeval-identifier` | `str` | — | Custom identifier for the DeepEval test run |

---

### `quick-eval`
Quick local evaluation (llama-cpp-python).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--adapter PATH` | `str` | *required* | Path to LoRA adapter directory |
| `--samples`, `-n N` | `int` | `20` | Number of validation samples |
| `--spec`, `-s PATH` | `str` | *required* | Subject spec JSON |
| `--val-data PATH` | `str` | *auto-detected* | Validation JSONL |
| `--output PATH` | `str` | `eval/results/{key}_eval_report.json` | Output report path |
| `--feedback-json PATH` | `str` | — | Save structured per-concept eval results |

---

### `track`
Track or show evaluation results.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--npc-key KEY` | `str` | — | NPC key |
| `--model PATH` | `str` | — | Model GGUF path |
| `--show` | `bool` | `False` | Show evaluation history |
| `--win-rate T` | `float` | — | Win rate vs baseline (0–1) |
| `--avg-quality T` | `float` | — | Average quality score |
| `--val-loss T` | `float` | — | Validation loss |
| `--notes TEXT` | `str` | `""` | Notes about this run |

---

### `compare-runs`
Compare two training runs by run_id.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `npc_key` (positional) | `str` | *required* | NPC key |
| `--baseline-run ID` | `str` | *required* | Baseline run ID |
| `--candidate-run ID` | `str` | *required* | Candidate run ID |
| `--spec PATH` | `str` | *auto-detected* | Subject spec |
| `--num-questions N` | `int` | `10` | Number of eval questions |
| `--judge` | `bool` | `False` | Use local Ollama judge |

---

### `feedback`
Run the self-improving feedback loop.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `feedback_json` (pos.) | `str` | *required* | Path to feedback JSON from `evaluate --feedback-json` |
| `--win-rate-threshold T` | `float` | `0.5` | Min win rate |
| `--quality-threshold T` | `float` | `25.0` | Max quality score (lower = better) |
| `--violation-threshold N` | `int` | `1` | Max constraint violations |
| `--dry-run` | `bool` | `False` | Analyze without regenerating |
| `--auto`, `-y` | `bool` | `False` | Auto-accept all suggestions |
| `--skip-gap-detection` | `bool` | `False` | Skip knowledge coverage check |
| `--save-gaps PATH` | `str` | — | Save knowledge gap report to JSON |
| `--json` | `bool` | `False` | Output machine-readable JSON summary |
| `--auto-retrain` | `bool` | `False` | After regeneration, auto-retrain and re-evaluate |
| `--train-preset PRESET` | `str` | `fast-3b` | Training preset for auto-retrain |
| `--baseline PATH` | `str` | — | Baseline GGUF for auto-evaluation after retrain |
| `--regeneration-technique TECH` | `str` | `template` | `template`, `ollama` |
| `--regeneration-preset PRESET` | `str` | *auto (presets)* | `generate-qwen25`, `generate-llama31`, `generate-qwen35-exp`, `generate-qwen3-exp` |
| `--regeneration-model MODEL` | `str` | `qwen2.5:7b` | Exact Ollama regeneration model (wins over preset) |
| `--regeneration-url URL` | `str` | `http://localhost:11434` | Ollama base URL for regeneration |
| `--regeneration-batch-size N` | `int` | `4` | Ollama batch size for regeneration |
| `--deepeval-judge-preset PRESET` | `str` | *auto (presets)* | `judge-qwen25`, `judge-llama31-exp`, `judge-qwen35-exp`, `judge-qwen3-exp` |
| `--deepeval-judge-model MODEL` | `str` | — | Exact Ollama judge model (wins over preset) |
| `--deepeval-ollama-url URL` | `str` | `http://localhost:11434` | Ollama base URL for DeepEval |
| `--deepeval-cases-per-category N` | `int` | `1` | Cases per category for fast DeepEval |
| `--deepeval-soft-fail` | `bool` | `False` | Do not abort dataset eval on metric failure |
| `--wandb` | `bool` | `False` | Enable W&B logging |
| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |

---

### `pipeline`
Run the full canonical pipeline: validate-spec → generate → sanitize → dataset-eval → train → export → smoke-test → evaluate.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
| `--preset PRESET` | `str` | `fast-3b` | Training preset |
| `--ollama` | `bool` | `False` | Shortcut for `--technique ollama` |
| `--technique TECH` | `str` | `template` | `docs`, `ollama`, `template`, `openai`, `anthropic` |
| `--docs-manifest PATH` | `str` | — | Docs corpus manifest for `--technique docs` |
| `--model MODEL` | `str` | — | LLM model name for generation stage |
| `--track` | `bool` | `False` | Track results in Supabase |
| `--wandb` | `bool` | `False` | Enable W&B logging during training |
| `--full-merge-export` | `bool` | `False` | Full merge export (standalone GGUF) |
| `--skip-smoke` | `bool` | `False` | Skip smoke test phase |
| `--skip-eval` | `bool` | `False` | Skip evaluation phase |
| `--skip-spec-validate` | `bool` | `False` | Skip spec generation-ready validation |
| `--skip-dataset-eval` | `bool` | `False` | Skip DeepEval dataset quality gate |
| `--dataset-eval-mode` | `str` | `fast` | `fast`, `release` |
| `--dataset-eval-cases-per-category N` | `int` | *mode-dep.* | Rows sampled per category for pipeline dataset-eval |
| `--num-eval-questions N` | `int` | `5` | Number of evaluation questions |

---

### `plan-execution`
Recommend local vs remote (Colab) for generation/training.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec PATH` | `str` | *required* | Path to subject spec JSON |
| `--preset PRESET` | `str` | — | Training preset |
| `--local-vram-gb GB` | `float` | *auto-detected* | Override detected local VRAM |
| `--json` | `bool` | `False` | Output JSON |

---

### `plan-batch`
Batch plan local vs remote queues and generate Colab notebooks.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--spec-glob GLOB` | `str` | `data/npcs/specs/*.json` | Spec glob under project root |
| `--spec PATH` (repeatable) | `str[]` | — | Explicit spec path (repeatable) |
| `--presets PRESETS` | `str` | `fast-3b` | Comma-separated presets |
| `--local-vram-gb GB` | `float` | — | Override detected local VRAM |
| `--json` | `bool` | `False` | Output JSON |
| `--write-plan PATH` | `str` | — | Write plan JSON to file |
| `--generate-colab-notebooks` | `bool` | `False` | Generate notebooks for remote queue |
| `--colab-output-dir PATH` | `str` | `colab/outputs` | Notebook output directory |
| `--drive-repo-dir PATH` | `str` | `/content/drive/MyDrive/Unsloth_Core` | Drive path where repo is cloned |

---

### `batch-export`
Export all NPCs to GGUF without reloading base model between NPCs.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--npc KEYS` | `str` | *auto-detect* | Comma-separated NPC keys |
| `--quantization TYPE` | `str` | `q4_k_m` | GGUF quantization |
| `--model MODEL` | `str` | *auto-detected* | Base model ID |
| `--skip-f16` | `bool` | `False` | Skip f16 variants |

---

### `tb-reader`
Read TensorBoard event files as JSON.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--run-dir PATH` | `str` | *required* | Path to TensorBoard event directory |
| `--indent N` | `int` | `2` | JSON indent |

---

### `init` / `new-npc`
Scaffold a new NPC (folders + spec).

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `npc_key` (positional) | `str` | *required* | NPC key (snake_case) |
| `--subject TEXT` | `str` | — | Subject description |
| `--name TEXT` | `str` | — | NPC display name |
| `--force` | `bool` | `False` | Overwrite existing spec |
| `--skip-spec` | `bool` | `False` | Only create folders, skip spec file |

---

### `audit`
Health check and context audit.

| Subcommand | Description | Flags |
|-----------|-------------|-------|
| `audit check` | Quick environment health check | `--full` (bool: full audit) |
| `audit diagnose` | Diagnose NPC issue | `--npc KEY` (required) |
| `audit resume` | Recover session context (full audit) | — |

---

### `supabase-check`
Verify NPC profile + dialogue memory path in Supabase.

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--npc-key KEY` | `str` | *required* | NPC key |
| `--player-id UUID` | `str` | — | Probe player UUID |
| `--skip-probe` | `bool` | `False` | Only profile alignment, skip dialogue probe |

---

### `pipeline` (Legacy / Subcommands not listed above)

---

## 2. Dataset Categories & Contract Constants

Defined in `scripts/dataset/dataset_contracts.py`.

### 5 Supported Categories

| Category | Description | Min Examples (SFT) | Role |
|----------|-------------|-------------------:|------|
| `identity` | Persona introduction and self-identification | **8** | Defines NPC character, personality, background |
| `teaching` | Subject-matter explanations | **32** | Core knowledge transfer (largest category) |
| `dialogue` | Natural conversation handling | **16** | Clarification, deep-dives, follow-ups |
| `quest` | Scenario-based interactions | **8** | Challenges, practice problems, quizzes |
| `refusal` | Safe boundary responses | **8** | Polite refusal, scope-limiting, safety guardrails |
| **Total** | | **72** | |

### 3 Difficulty Levels

| Level | Used for |
|-------|----------|
| `beginner` | Simple explanations, foundational concepts |
| `intermediate` | Deeper analysis, comparative questions |
| `advanced` | Expert-level nuance, edge cases, synthesis |

### Contract Helpers

| Function | Purpose |
|----------|---------|
| `expected_examples_per_category(spec)` | Returns target counts from spec or minimum contract |
| `generation_request_counts_for_training_targets(targets, val_split, include_validation)` | Inflates generation counts to account for validation holdout |
| `summarize_jsonl_dataset(path)` | Returns category/difficulty/concept distribution, content hash |
| `calculate_distribution_gaps(expected, observed)` | Returns underfilled categories with shortfall counts |
| `dataset_contract_from_spec(spec)` | Builds machine-readable contract block: categories, minimums, difficulties |
| `file_sha256(path)` | Returns `sha256:{hex}` content hash |
| `record_pipeline_stage()` | One-shot helper to record a pipeline stage to `.pipeline/run_manifest.json` |

---

## 3. Generation Techniques

| Technique | Description | Backend |
|-----------|-------------|---------|
| `template` | Fast deterministic generation from curated prompt templates | Built-in Jinja-like templates (`generation_profiles.py`) |
| `docs` | Grounded generation from curated reference-doc manifests | Reference docs in `data/npcs/reference_docs/` |
| `ollama` | LLM-driven synthetic data via local Ollama | Ollama API (`http://localhost:11434`) |
| `openai` | LLM-driven synthetic data via OpenAI API | OpenAI chat completions |
| `anthropic` | LLM-driven synthetic data via Anthropic API | Anthropic messages API |

### Category Templates (from `generation_profiles.py`)

| Category | User Template Count | Assistant Generator |
|----------|:-------------------:|---------------------|
| `identity` | 8 | `generate_identity_response(spec)` |
| `teaching` | 32 | `generate_teaching_response(spec, concept_a, concept_b, difficulty, retriever)` |
| `dialogue` | 16 | `generate_dialogue_response(spec, concept, dialogue_type, retriever)` |
| `quest` | 8 | `generate_quest_response(spec, concept, scenario_name, retriever)` |
| `refusal` | 8 | `generate_refusal_response(spec, boundary)` |

### DialogueGuardrail Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_sentences` | `5` | Max sentences in NPC response |
| `max_characters` | `500` | Max characters in NPC response |
| `allow_formatting` | `True` | Allow markdown bolding, headers, lists |

### Refusal Boundary Types

| Boundary Pattern | Handler |
|-----------------|---------|
| `speculate` / `counterfactual` | Labels as speculation, redirects to documented facts |
| `misinformation` / `conspiracy` | Declines, redirects to evidence-based sources |
| `unsupported_certainty` / `date range` | Gives ranges, declines false precision |
| `medical` / `dietary` | Declines, redirects to safe cooking/exercise basics |
| `unsafe` / `food preparation` | Declines unsafe methods, offers safe alternatives |
| `aliens` / `extraterrestrial` | Declines, redirects to astronomy facts |
| `topic change` / `different topic` | Allows topic switch within subject scope |

---

## 4. Ollama Model Presets

Defined in `configs/ollama-model-presets.yaml`, resolved by `scripts/ops/ollama_model_presets.py`.

### Generation Presets

| Preset Name | Resolved Model | Params | Use Case |
|-------------|---------------|:------:|----------|
| `generate-qwen25` | `qwen2.5:7b` | 7B | **Default generation** (balanced speed/quality) |
| `generate-llama31` | `llama3.1:8b` | 8B | Alternative generation model |
| `generate-qwen35-exp` | `qwen3.5:latest` | ~8B | Experimental — latest Qwen 3.5 |
| `generate-qwen3-exp` | `qwen3:latest` | 8.2B | Qwen 3 (also used as judge) |

### Judge Presets

| Preset Name | Resolved Model | Params | Use Case |
|-------------|---------------|:------:|----------|
| `judge-qwen25` | `qwen2.5:7b` | 7B | Alternative judge |
| `judge-llama31-exp` | `llama3.1:8b` | 8B | Experimental judge |
| `judge-qwen35-exp` | `qwen3.5:latest` | ~8B | Experimental — latest Qwen 3.5 |
| `judge-qwen3-exp` | `qwen3:latest` | 8.2B | Experimental — Qwen 3 |

### Defaults & Resolution

| Constant | Value |
|----------|-------|
| Default generation preset | `generate-qwen25` → `qwen2.5:7b` |
| Default judge preset | `judge-qwen25` → `qwen2.5:7b` |
| Safety fallback (judge) | `qwen2.5:7b` |
| Safety fallback (generation) | `qwen2.5:7b` |

**Resolution priority** (`resolve_ollama_model()`):
1. Explicit CLI `--model` (wins unconditionally)
2. Explicit CLI `--preset` (maps through YAML)
3. Role-specific default preset (`default_generation` / `default_judge`)
4. Safety fallback model

### Ollama Serving Configuration

| Env Variable | Value | Effect |
|-------------|-------|--------|
| `OLLAMA_NUM_PARALLEL` | `4` | 4 concurrent request slots |
| `OLLAMA_FLASH_ATTENTION` | `1` | Enables flash attention |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | 8-bit KV cache |

---

## 5. Training Presets

Defined in `configs/presets/*.yaml`. Merged on top of `configs/lora-sft-base.yaml`.

### Preset Comparison Table

| Parameter | Base YAML | `smoke` | `fast-3b` | `fast-1.7b` | `safe-any` | `premium-3b` | `remote-3b-quality` |
|-----------|:---------:|:-------:|:---------:|:-----------:|:----------:|:------------:|:-------------------:|
| **Target GPU** | 6GB | any | 6GB | 6GB | any | 15GB+ (T4/L4) | Colab |
| **Model** | Llama-3.2-3B | *inherits* | *inherits* | *inherits* | *inherits* | *inherits* | **Llama-3.2-3B** (explicit) |
| **max_steps** | — | **10** | — | — | — | — | — |
| **num_epochs** | 3 | **1** | 3 | 3 | 3 | 3 | **5** |
| **batch_size** | 1 | **1** | **1** | **1** | **1** | **4** | **4** |
| **gradient_accumulation_steps** | 8 | **2** | **8** | **4** | **8** | **4** | **4** |
| **effective batch size** | 8 | 2 | 8 | 4 | 8 | 16 | 16 |
| **max_seq_length** | 2048 | **512** | 2048 | **1024** | **1024** | 2048 | **2048** |
| **learning_rate** | 0.0002 | 0.0002 | 0.0002 | 0.0002 | 0.0002 | **0.0002** | **0.00015** |
| **warmup_steps** | 10 | — | 10 | **10** | **5** | **20** | **30** |
| **save_steps** | 50 | **5** | 50 | 50 | 50 | 50 | **25** |
| **eval_steps** | 50 | **5** | 50 | 50 | 50 | 50 | **25** |
| **weight_decay** | 0.01 | 0.01 | 0.01 | 0.01 | 0.01 | 0.01 | **0.01** |
| **packing** | true | true | true | true | true | true | **true** |
| **train_on_responses_only** | true | true | true | true | true | true | **true** |
| **lr_scheduler_type** | linear | linear | linear | linear | linear | linear | **cosine** |
| **LoRA r** | 16 | **8** | **16** | **16** | **8** | **32** | **64** |
| **LoRA alpha** | 32 | **16** | **32** | **32** | **16** | **64** | **128** |
| **LoRA dropout** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | **0.05** | **0.05** |
| **target_modules** | full set | *inherits* | *inherits* | *inherits* | *inherits* | *inherits* | **full set** (explicit) |
| **W&B enabled** | false | false | false | false | false | false | **true** |

### Preset Selection Heuristic

| Condition | Chosen Preset |
|-----------|---------------|
| Debug/testing | `smoke` |
| 3B model, VRAM ≥ 10GB | `fast-3b` |
| 1.5B–1.7B model, VRAM ≥ 6GB | `fast-1.7b` |
| Any size, limited VRAM (or auto-fallback) | `safe-any` |
| 15GB+ VRAM (T4/L4 Colab) | `premium-3b` |
| Remote execution, maximum quality | `remote-3b-quality` |

### LoRA Target Modules (default)

```
q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
```

### W&B Preset (`wandb.yaml`)

| Key | Value |
|-----|-------|
| `wandb.enabled` | `true` |

Simple override that flips W&B on for any base config.

---

## 6. Training Parameters (from base YAML)

Defined in `configs/lora-sft-base.yaml` — the full schema merged with presets at runtime.

### Model Section

| Key | Default | Description |
|-----|---------|-------------|
| `model` | `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` | Base HuggingFace model ID |

### Data Section

| Key | Default | Description |
|-----|---------|-------------|
| `data.format_type` | `chatml` | ChatML format for training data |

### Training Section

| Key | Default | Description |
|-----|---------|-------------|
| `training.training_type` | `lora` | Training type (only LoRA supported) |
| `training.max_seq_length` | `2048` | Max sequence length (tokens) |
| `training.load_in_4bit` | `true` | 4-bit quantization (QLoRA) |
| `training.num_epochs` | `3` | Number of training epochs |
| `training.learning_rate` | `0.0002` | AdamW learning rate |
| `training.batch_size` | `1` | Per-device batch size |
| `training.gradient_accumulation_steps` | `8` | Gradient accumulation steps |
| `training.warmup_steps` | `10` | Linear warmup steps |
| `training.save_steps` | `50` | Checkpoint save interval |
| `training.eval_steps` | `50` | Evaluation interval |
| `training.weight_decay` | `0.01` | AdamW weight decay |
| `training.packing` | `true` | Pack multiple sequences into one |
| `training.train_on_responses_only` | `true` | Mask loss on user turns |

### Additional Runtime Training Parameters

| Parameter | Location | Effect |
|-----------|----------|--------|
| `training.max_steps` | Presets | Override epochs with max step count (`smoke`: 10) |
| `training.lr_scheduler_type` | Presets | Scheduler type (`cosine` in `remote-3b-quality`) |

### LoRA Section

| Key | Default | Description |
|-----|---------|-------------|
| `lora.r` | `16` | LoRA rank |
| `lora.alpha` | `32` | LoRA alpha scaling |
| `lora.dropout` | `0.0` | LoRA dropout rate |
| `lora.target_modules` | `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj` | Comma-separated target module list |

### Logging Section

| Key | Default | Description |
|-----|---------|-------------|
| `logging.enable_tensorboard` | `true` | Enable TensorBoard logging |

---

## 7. Sanitize Settings

Parameters applied by `scripts/dataset/sanitize_dataset.py` (invoked via `ucore sanitize`).

### Structural Validation

| Setting | Default | Description |
|---------|---------|-------------|
| `--min-length` | `10` | Min chars for assistant response |
| `--max-sentences` | `5` | Max sentences for assistant response |
| `--strict-mode` | `False` | Raise on structural errors vs discard |
| `--artifact-check` | `strict` | AI artifact handling: `strict`, `warn`, `off` |
| `--verbose-artifacts` | `False` | Show exact artifact pattern matched |

### AI Artifact Patterns (checked in responses)

| Pattern | Example |
|---------|---------|
| AI disclaimers | `"as an ai"`, `"as a language model"`, `"i don't have personal feelings"` |
| Vendor mentions | `"openai"`, `"anthropic"` |
| Meta-references | `"knowledge cutoff"`, `"from my training data"`, `"i'm just an ai"` |

### Quality Scoring

| Setting | Default | Description |
|---------|---------|-------------|
| `--quality-threshold-pass` | `70` | Minimum total score to pass |
| `--quality-threshold-flag` | `50` | Below this, examples flagged for review |
| `--discard-below-score` | `0` | Discard examples below this score (0 = keep all) |
| `--quality-report` | `False` | Print quality score distribution |

### Metadata Handling

| Setting | Default | Description |
|---------|---------|-------------|
| `--no-fix-metadata` | `False` | Disable auto-repair of missing metadata fields |
| `--require-complete-metadata` | `False` | Error out if any metadata field missing |
| `--write-manifest` / `--no-write-manifest` | `True` | Enable/disable enriched manifest writing |
| `--manifest-path PATH` | — | Override manifest output path |

### Deduplication

| Setting | Default | Description |
|---------|---------|-------------|
| `--dedup` / `--no-dedup` | `True` | Enable/disable content_hash deduplication |
| `--dedup-report` | `False` | Show which content hashes removed |

### Output & Debug

| Setting | Default | Description |
|---------|---------|-------------|
| `--output`, `-o` | `*_clean.jsonl` | Output JSONL path |
| `--verbose`, `-v` | `False` | Print discarded examples and metadata warnings |
| `--spec PATH` | — | NPC spec JSON for better quality scoring |
| `--strict-canonical` | `False` | Require canonical dataset path |
| `--debug` | `False` | Re-raise exceptions with traceback |

---

## 8. Dataset Eval (DeepEval) Settings

Parameters for `scripts/dataset/dataset_eval.py` (invoked via `ucore dataset-eval`).

### Mode-Dependent Defaults

| Parameter | `fast` mode | `release` mode |
|-----------|:-----------:|:--------------:|
| `--cases-per-category` | 1 | 5 |
| Blocking on metric failure | No (diagnostics only) | Yes |
| Use case | Iteration-friendly | Strict final checks |

### All Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--mode` | `str` | `fast` | `fast`, `release` |
| `--judge-model MODEL` | `str` | *resolved from presets* | Local Ollama judge model |
| `--judge-preset PRESET` | `str` | *resolved from presets* | Named Ollama judge preset |
| `--ollama-base-url URL` | `str` | `http://localhost:11434` | Ollama server URL |
| `--judge-temperature T` | `float` | `0.0` | Judge temperature |
| `--cases-per-category N` | `int` | *mode-dep.* | Rows sampled per category |
| `--categories CATS` | `str` | — | Comma-separated category filter |
| `--identifier ID` | `str` | — | DeepEval run identifier |
| `--display` | `str` | `all` | `all`, `failing`, `passing` |
| `--ignore-errors` | `bool` | `False` | Continue when individual metric calls error |
| `--soft-fail` | `bool` | `False` | Write artifacts but return 0 even on failures |
| `--output PATH` | `str` | — | Quality summary JSON path |
| `--technique TECH` | `str` | `template` | Dataset technique to evaluate |
| `--confident` | `bool` | `False` | Enforce that CONFIDENT_API_KEY is configured (exits with error if missing) |

### Quality Gate Checks (in `train.py`)

| Check | Blocks Training |
|-------|:---------------:|
| Dataset is `train_clean.jsonl` (not raw `train.jsonl`) | Yes |
| `quality_summary.json` exists with `status: "ok"` | Yes |
| Zero distribution gaps | Yes |
| Zero unknown rows | Yes |
| Clean sanitizer quality signals | Yes |
| Matching dataset content hash | Yes |
| Failing sampled DeepEval cases (`release` mode) | Yes |
| Failing sampled DeepEval cases (`fast` mode) | **No** (diagnostics only) |

### Opt-Out

| Flag | Effect |
|------|--------|
| `--allow-ungated-dataset` | Skip all quality gate checks |
| `--deepeval-soft-fail` | Run DeepEval but don't fail on metric failures |
| `--skip-dataset-eval` | Skip running DeepEval entirely |

---

## 9. Evaluation Settings (./ucore evaluate)

Parameters for `scripts/evaluation/evaluate.py`.

### Eval Presets (from `configs/eval-presets.yaml`)

| Preset | Questions | Judge | HTML Report | Description |
|--------|:---------:|:-----:|:-----------:|-------------|
| `smoke` | 3 | No | No | Fast smoke test |
| `quick` | 10 | No | No | Quick check |
| `full` | 25 | Yes | Yes | Full evaluation |

### All Evaluate Flags

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--baseline PATH` | `str` | — | Baseline GGUF model path |
| `--candidate PATH` | `str` | — | Candidate GGUF model path |
| `--model`, `-m PATH` | `str` | — | Single model (interactive) |
| `--spec`, `-s PATH` | `str` | — | Subject spec JSON |
| `--val-data PATH` | `str` | — | Validation JSONL |
| `--num-questions N` | `int` | `10` | Number of eval questions |
| `--output`, `-o PATH` | `str` | — | Output report path |
| `--report-html` | `bool` | `False` | Generate HTML report (Chart.js) |
| `--judge` | `bool` | `False` | Use local Ollama judge |
| `--judge-model MODEL` | `str` | `llama3.1:latest` | Judge model |
| `--track` | `bool` | `False` | Track in `eval/results/` |
| `--interactive`, `-i` | `bool` | `False` | Interactive chat mode |
| `--training-metrics [PATH]` | `str` | — | Show TensorBoard metrics |
| `--deepeval` | `bool` | `False` | Run DeepEval model quality evaluation after conventional eval |
| `--deepeval-judge-model` | `str` | `qwen3:latest` | Ollama model to use as judge |
| `--deepeval-identifier` | `str` | — | Custom identifier for the DeepEval test run |

### Inference Engine Flags

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--port N` | `int` | `8888` | llama-server port |
| `--gpu-layers N` | `int` | `99` | GPU layers (0 = CPU-only) |
| `--max-tokens N` | `int` | `256` | Max generated tokens |
| `--host ADDR` | `str` | `127.0.0.1` | llama-server host |
| `--base-model PATH` | `str` | — | Base GGUF for LoRA eval |
| `--lora-weight T` | `float` | `1.0` | LoRA adapter weight |

### Feedback Integration

| Flag | Description |
|------|-------------|
| `--feedback-json PATH` | Save structured per-concept eval results for feedback loop |
| `--npc-key KEY` | NPC key for TensorBoard runs lookup |

---

## 10. Feedback Loop Settings

Parameters for `scripts/training/feedback_loop.py` (invoked via `ucore feedback`).

### Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--win-rate-threshold` | `0.5` | Min win rate vs baseline |
| `--quality-threshold` | `25.0` | Max quality score (lower = better) |
| `--violation-threshold` | `1` | Max constraint violations |

### Execution Control

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--dry-run` | `False` | Analyze without regenerating |
| `--auto`, `-y` | `False` | Auto-accept all suggestions |
| `--skip-gap-detection` | `False` | Skip knowledge coverage check |
| `--save-gaps PATH` | — | Save knowledge gap report to JSON |
| `--json` | `False` | Machine-readable JSON summary |
| `--auto-retrain` | `False` | After regeneration, auto-retrain and re-evaluate |
| `--train-preset` | `fast-3b` | Training preset for auto-retrain |
| `--baseline PATH` | — | Baseline GGUF for auto-evaluation |

### Regeneration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--regeneration-technique` | `template` | `template`, `ollama` |
| `--regeneration-preset` | `generate-qwen25` | Ollama generation preset |
| `--regeneration-model` | `qwen2.5:7b` | Exact Ollama regeneration model |
| `--regeneration-url` | `http://localhost:11434` | Ollama base URL for regeneration |
| `--regeneration-batch-size` | `4` | Ollama batch size |

### DeepEval Parameters (Post-Regeneration)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--deepeval-judge-preset` | *resolved* | Named Ollama judge preset |
| `--deepeval-judge-model` | — | Exact Ollama judge model |
| `--deepeval-ollama-url` | `http://localhost:11434` | Ollama base URL for DeepEval |
| `--deepeval-cases-per-category` | `1` | Cases per category for fast DeepEval |
| `--deepeval-soft-fail` | `False` | Don't abort dataset evaluation on metric failure |

### Knowledge Gap Detection

| Gap Type | Cause | Fix |
|----------|-------|-----|
| `training_density` | Not enough training examples | Regenerate with `--concept-focus` |
| `knowledge_gap` | Missing reference material | Add reference docs + re-index |

---

## 11. Preflight / Preheat Settings

Parameters for `scripts/ops/preflight.py`.

### CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--phase` | `str` | `train` | `train`, `dataset_eval`, `export` |
| `--preset PRESET` | `str` | — | Requested training preset |
| `--spec PATH` | `str` | — | Subject spec JSON path |
| `--technique TECH` | `str` | — | Dataset technique name |
| `--ollama-url URL` | `str` | `http://localhost:11434` | Ollama server URL |
| `--no-auto-unload-ollama` | `bool` | `False` | Do not stop running Ollama models |
| `--no-gcc-check` | `bool` | `False` | Skip gcc validation even for training |
| `--json` | `bool` | `False` | Print JSON only |

### Checks Performed

| Check | Description | Phase Required |
|-------|-------------|:-------------:|
| GPU memory inventory | `nvidia-smi` free/total VRAM in GiB | All |
| Auto-downgrade VRAM | `fast-3b` → `safe-any` when total VRAM < 10GB | `train` |
| Ollama auto-unload | Detect + stop running Ollama models | `train`, `dataset_eval` |
| GCC toolchain | Verify `gcc` in PATH (Triton requirement) | `train` |

### PreflightReport Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | `"ok"`, `"degraded"`, `"blocked"` |
| `phase` | `str` | Pipeline phase |
| `preset_requested` | `str` | What was asked for |
| `preset_effective` | `str` | What will actually run |
| `technique` | `str` | Dataset technique |
| `total_vram_gb` | `float` | Total GPU VRAM (GiB) |
| `free_vram_gb` | `float` | Free GPU VRAM (GiB) |
| `gcc_ok` | `bool` | GCC available |
| `gcc_path` | `str` | GCC binary path |
| `running_ollama_models` | `list[str]` | Models detected running |
| `stopped_ollama_models` | `list[str]` | Models auto-stopped |
| `recommendation.training.location` | `str` | `"local"` or `"remote_colab"` |
| `recommendation.training.reason` | `str` | Why that location was chosen |
| `warnings` | `list[str]` | Non-blocking issues |
| `errors` | `list[str]` | Blocking issues |

---

## 12. Model Size → Preset Mapping

Defined in `configs/model-presets.yaml`.

### Exact Model Mappings

| Model ID | Preset |
|----------|--------|
| `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` | `fast-3b` |
| `unsloth/Llama-3.2-1B-Instruct-bnb-4bit` | `safe-any` |
| `unsloth/Qwen3-1.7B-unsloth-bnb-4bit` | `fast-1.7b` |
| `unsloth/Llama-3.1-8B-Instruct-bnb-4bit` | `premium-3b` |

### Size Bucket Mappings

| Model Size Bucket | Preset | Typical VRAM (4-bit LoRA) |
|:-----------------:|--------|:-------------------------:|
| `0.5b` | `safe-any` | 2.0 GB |
| `1b` | `safe-any` | 2.5 GB |
| `1.7b` | `fast-1.7b` | 3.5 GB |
| `3b` | `fast-3b` | 5.0 GB |
| `7b` | `premium-3b` | 12.0 GB |
| `8b` | `premium-3b` | 14.0 GB |

### Resolution Logic

1. **Exact model ID** match in `exact_models` → use directly
2. **Size bucket** heuristic → use mapped preset
3. **Default** → `fast-3b`

---

## 13. Workload Policy

Defined in `configs/workload-policy.yaml`.

### Safety Parameters

| Key | Value | Description |
|-----|:-----:|-------------|
| `safety.training_vram_safety_margin` | `1.25` | Require local VRAM to exceed estimate by this multiplier |
| `local_caps.ollama_min_vram_gb` | `6` | If Ollama generation selected and VRAM < 6GB, prefer remote |

### Model VRAM Baselines (4-bit LoRA, observed)

| Size | Baseline VRAM |
|:----:|:-------------:|
| 0.5b | 2.0 GB |
| 1b | 2.5 GB |
| 1.7b | 3.5 GB |
| 3b | 5.0 GB |
| 7b | 12.0 GB |
| 8b | 14.0 GB |

### Policy Notes

- Baselines reflect observed Unsloth 4-bit LoRA behavior on RTX 3060 6GB workflow
- Use `--preset safe-any` if local run OOMs
- Prefer W&B/PeerLM remote credits for reporting/evaluation (not Colab/Kaggle training)

---

## 14. Promotion Rules

Defined in `configs/promotion-rules.yaml`. A model must pass **ALL** thresholds before being promoted to "best".

| Threshold | Value | Description |
|-----------|:-----:|-------------|
| `max_training_loss` | `2.0` | Max final training loss (Onyx v2 converges ~1.76–1.80) |
| `min_eff_batch_size` | `4` | Minimum effective batch size |
| `min_train_examples` | `10` | Minimum number of training examples |

These prevent garbage models from being promoted due to NaN loss or bad config.

---

## 15. Export Settings

### Adapter Export (Default, for LLMUnity)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--outtype` | `f16` | Output format: `f32`, `f16`, `bf16`, `q8_0` |
| Script | `convert_lora_to_gguf.py` | Prebuilt in `~/.unsloth/llama.cpp/` |
| Output size | ~MBs | Lightweight LoRA weights only |
| Unity usage | `--lora` flag on `llama-server` | No base model needed in export |

### Full-Merge Export (Standalone GGUF)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--full-merge` | `False` | Produce standalone merged GGUF |
| `--quantization` | `q4_k_m` | GGUF quantization type |
| `--skip-f16` | `False` | Skip f16 variant in full-merge mode |
| `--maximum-memory GB` | — | Max memory for `save_pretrained_gguf` |
| Quantization binary | `llama-quantize` | Prebuilt in `~/.unsloth/llama.cpp/` |

### Output File Naming

| Mode | Pattern |
|------|---------|
| Adapter | `{npc_key}-lora-f16.gguf` |
| Full-merge | `{npc_key}-{model_short}-{quant}.gguf` |

### Batch Export (`ucore batch-export`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--npc` | *auto-detect* | Comma-separated NPC keys |
| `--quantization` | `q4_k_m` | GGUF quantization |
| `--model` | *auto-detected* | Base model ID |
| `--skip-f16` | `False` | Skip f16 variants |

### Deploy to Unity (`ucore deploy`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--unity-project` | *auto-detected* | Path to Unity project |
| `--dry-run` | `False` | Show what would be done without copying |
| `--skip-export` | `False` | Skip GGUF export step |
| `--export-only` | `False` | Only export, skip Unity copy |

---

## 16. Engine / Inference Settings

### llama-server (used by evaluate.py)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--port` | `8888` | Server listening port |
| `--gpu-layers` | `99` | GPU layers to offload (0 = CPU-only) |
| `--host` | `127.0.0.1` | Bind address |
| `--lora` | *(adapter path)* | Load LoRA adapter GGUF |
| `--lora-weight` | `1.0` | LoRA adapter weight |

### Location

| Binary | Path |
|--------|------|
| `llama-server` | `~/.unsloth/llama.cpp/llama-server` |
| `llama-quantize` | `~/.unsloth/llama.cpp/llama-quantize` |
| `convert_lora_to_gguf.py` | `~/.unsloth/llama.cpp/convert_lora_to_gguf.py` |

---

## 17. W&B Settings

### Global Config (from `lora-sft-base.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `wandb.enabled` | `false` | Master switch |
| `wandb.project` | `unsloth-core` | W&B project name |
| `wandb.entity` | `andreabenathar-twl-games` | W&B entity/username |
| `wandb.tags` | `[]` | Tags attached to runs |

### CLI Override Flags

| Flag | Description |
|------|-------------|
| `--wandb` | Enable W&B (overrides config `false`) |
| `--no-wandb` | Disable W&B (overrides config `true`) |
| `--wandb-project NAME` | Override W&B project |
| `--wandb-entity ENTITY` | Override W&B entity |

### Pipeline Auto-Group

```python
WANDB_GROUP = f"pipeline-{npc_key}-{timestamp}"
```

Set as `WANDB_GROUP` and `WANDB_RUN_GROUP` env vars when `--wandb` is passed to `ucore pipeline`.

### W&B Artifacts Logged

| Artifact Type | Content | Versioned By |
|---------------|---------|-------------|
| Dataset artifact | Dataset JSONL | Content hash, technique, row count |
| LoRA artifact | Final adapter weights | `lora-{npc_key}` |
| GGUF artifact | Exported GGUF | `gguf-{npc_key}` |
| Config snapshot | Frozen training config | Run file |

---

## 18. CLI Global Flags

| Flag | Scope | Env Var | Description |
|------|-------|---------|-------------|
| `--workflow-hooks PATH` | All commands | `WORKFLOW_HOOKS_PATH` | Path to JSONL hook log for step tracing |
| `--watch` | All commands | `UCORE_WATCH=1` | Stream with early error alerts + watch log |
| `--watch` (auto-detected) | All commands | `UCORE_WATCH_DIR` | Watch log directory (default: system tempdir) |

### Early Alert Patterns (built into `--watch` mode)

| Pattern | Matches |
|---------|---------|
| `Traceback (most recent call last):` | Python tracebacks |
| `AssertionError`, `ModuleNotFoundError`, `RuntimeError`, `ValueError`, `KeyError`, `IndexError`, `CalledProcessError`, `OSError` | Common Python errors |
| `ERROR`, `Error:`, `FAILED`, `FAILURE` | General error indicators |
| `Command timed out`, `timed out after` | Timeout events |
| `^\s*F\s+🎯 Evaluating test case` | DeepEval test failures |

---

## 19. Spec Validation Checks

Performed by `scripts/dataset/validate_subject_spec.py` (invoked via `ucore validate-spec`).

### Generation-Readiness Check (`--generation-ready`)

| Check | Fail Condition |
|-------|----------------|
| JSON parseable | Invalid JSON |
| `npc_key` present | Missing key |
| `reference_doc` path valid | File not found or unreadable |
| Reference doc meets contract | Missing H1, < 5 H2 sections, < 20 bullets, < 250 words, missing safety/refusal/boundary/misconception notes |
| All 5 categories have positive counts | Any category has 0 or negative count |
| All categories meet minimum SFT counts | Any category below `MIN_DATASET_EXAMPLES_PER_CATEGORY` |
| Dataset examples_per_category (if present) | Specifies counts below minimums |

### Individual Flag Checks

| Flag | Checks |
|------|--------|
| `--require-reference-docs` | `reference_doc` exists and is readable |
| `--require-reference-contract` | Reference doc meets generation-readiness minimums |
| `--require-all-categories` | All 5 dataset categories have positive counts |
| `--require-dataset-minimums` | All categories meet minimum SFT counts |
| `--generation-ready` | All of the above combined |

---

## 20. Environment Variables

| Variable | Set By | Used By | Description |
|----------|--------|---------|-------------|
| `WORKFLOW_HOOKS_PATH` | `ucore` / CLI | All pipeline scripts | Path to workflow hook JSONL file |
| `UCORE_WATCH` | `--watch` flag | `ucore` | Enable watch mode (`"1"`) |
| `UCORE_WATCH_DIR` | User | `ucore` | Watch log output directory |
| `WANDB_GROUP` | `ucore pipeline` | W&B | Pipeline run group (`pipeline-{key}-{ts}`) |
| `WANDB_RUN_GROUP` | `ucore pipeline` | W&B | Pipeline run group (alias) |
| `WANDB_JOB_TYPE` | `ucore pipeline` | W&B | Job type (`"train"` / `"eval"`) |
| `DEEPEVAL_OLLAMA_MODEL` | `dataset_eval.py` | DeepEval | Judge model for DeepEval |
| `PIPELINE_DB_URL` | User | `PipelineDB` | Direct PostgreSQL connection string |
| `SUPABASE_URL` | User | `PipelineDB` | Supabase REST API URL |
| `SUPABASE_SERVICE_KEY` | User | `PipelineDB` | Supabase service role key |
| `OLLAMA_NUM_PARALLEL` | Systemd | Ollama | Concurrent request slots (4) |
| `OLLAMA_FLASH_ATTENTION` | Systemd | Ollama | Flash attention enable (1) |
| `OLLAMA_KV_CACHE_TYPE` | Systemd | Ollama | KV cache quantization (`q8_0`) |

---

## Appendix A: Category Templates (generation_profiles.py) — Detailed Breakdown

### Identity Templates (8)

"Who are you?", "What is your name?", "Tell me about yourself.", "What should I call you?", "Are you a teacher?", "Who am I speaking with?", "What do you teach?", "Can you introduce yourself?"

### Teaching Templates (32)

`{concept}`-based: explain, tell me about, what is, how does, why is, example, I don't understand, key ideas behind, compare A and B, how is A related to B, difference between A and B, break down, where can I see, how do experts think, what should I know, real-world example, basics, something interesting, how did X come to be, what makes X useful, can you simplify, I'm struggling, common misconceptions, how do I apply, what do I need, describe like I'm five, main components, why does X matter, metaphor, history behind, how does X fit, advanced aspects.

### Dialogue Templates (16)

Clarification (re-explain), follow-up (deeper), example request, concept challenge, application question, memory elaboration, counter-argument, hypothetical, step-by-step, next-steps, cross-domain, alternate angle.

### Quest Templates (8)

Challenge, test knowledge, practice exercise, apply scenario, practice problem, quiz, real-world problem, difficult question.

### Refusal Templates (8 base, plus ~30 boundaries)

Poem request, meaning of life, baking cake, other-subject homework, stock advice, joke, lottery prediction, medical advice + boundary-specific refusals.

---

## Appendix B: Pipeline Script File Index

| ucore Command | Backend Script |
|---------------|---------------|
| `generate` | `scripts/dataset/generate_dataset.py` |
| `generate-ollama` | `scripts/dataset/generate_dataset_ollama.py` |
| `sanitize` | `scripts/dataset/sanitize_dataset.py` |
| `dataset-eval` | `scripts/dataset/dataset_eval.py` |
| `train` | `scripts/training/train.py` |
| `validate-spec` | `scripts/dataset/validate_subject_spec.py` |
| `validate-config` | `scripts/ops/validate_config.py` |
| `export` | `scripts/export/export.py` |
| `export-resume` | `scripts/export/export_resume.py` |
| `export-adapter` | `scripts/export/export_adapter.py` |
| `batch-export` | `scripts/export/batch_export.py` |
| `deploy` | `scripts/export/deploy_to_unity.py` |
| `evaluate` | `scripts/evaluation/evaluate.py` |
| `quick-eval` | `scripts/evaluation/quick_eval.py` |
| `track` | `scripts/evaluation/track_eval_results.py` |
| `compare-runs` | `scripts/evaluation/compare_runs.py` |
| `tb-reader` | `scripts/evaluation/tb_reader.py` |
| `feedback` | `scripts/training/feedback_loop.py` |
| `smoke` | `scripts/ops/smoke_test.py` |
| `init` / `new-npc` | `scripts/ops/scaffold_npc.py` |
| `audit` | `scripts/ops/audit.py` (inline) |
| `supabase-check` | `scripts/ops/supabase_integration_check.py` |
| `plan-execution` | `scripts/orchestration/plan_execution.py` |
| `plan-batch` | `scripts/orchestration/plan_batch_execution.py` |
| `pipeline` | `ucore` (inline orchestration, calls all above) |

---

> **Generated**: 2026-05-29
> **Source files consulted**: 18 files across `configs/`, `scripts/`, and root `ucore`
> **Total line count**: ~2,100 lines in source inputs

---

## Appendix C: Pipeline Utility Modules

| Module | Description | Type | Usage |
|--------|-------------|------|-------|
| `scripts/ops/env_loader.py` | Auto-sources `.env.local` across all pipeline scripts | Module | Imported |
| `scripts/ops/confident_push.py` | Push/pull datasets and goldens to/from Confident AI | Module | CLI / Library |
| `scripts/ops/pipeline_manifest.py` | Centralized pipeline run manifest tracking | Module | Library / CLI |
