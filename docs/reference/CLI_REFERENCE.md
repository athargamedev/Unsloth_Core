# CLI Reference: `./ucore`

The `ucore` tool is the unified entry point for the Unsloth_Core pipeline. It wraps the underlying Python scripts into a clean, command-driven interface.

## 🚀 The Pipeline Command
The easiest way to run the entire flow.
```bash
./ucore pipeline subjects/my_npc.json --preset fast-3b
```
**Stage**: `generate` -> `sanitize` -> `train` -> `export` -> `smoke`.

---

## 🏗️ Dataset Management

### `validate-spec`
Reviews subject specs before generation or training.
- `spec`: Path to one `subjects/*.json` file.
- `--all`: Validate every spec in `subjects/`; this is a repository-wide audit and can fail because checked-in draft or incomplete specs exist.
- `--json`: Emit machine-readable results with per-spec errors, warnings, and summary counts.
- `--strict`: Exit nonzero on warnings as well as errors.

```bash
./ucore validate-spec subjects/history_guide.json
./ucore validate-spec --all --json
```

### `generate`
Generates training data from a subject spec.
- `spec`: Path to JSON spec.
- `--technique`: `onyx` (default) for production datasets, `template` for smoke tests only.
- `--onyx-url`, `--onyx-api-key`, `--onyx-max-results`, `--onyx-max-context-chars`: Local Onyx retrieval settings for resource-conscious grounded generation.

The `onyx` technique retrieves from the local Onyx index and writes provenance-rich ChatML with bounded local resource use:

```bash
./ucore generate subjects/my_npc.json --technique onyx --onyx-max-results 3 --onyx-max-context-chars 1200
```

### `sanitize`
Validates and cleans a `.jsonl` dataset.
- `input`: Path to JSONL.
- `--strict-canonical`: Ensures the output path follows project conventions.

### `migrate-datasets`
Moves legacy flat datasets into the new canonical structure.

---

## 🎓 Training & Export

### `train`
Starts a LoRA fine-tuning session.
- `config_or_spec`: Path to spec or YAML config.
- `--from-spec`: Optional for `.json` subject files; `ucore train` auto-detects them.
- `--preset`: Choose from `configs/presets/` (`fast-3b`, `safe-any`, `smoke`, `wandb`).
- `--wandb`: Enable Weights & Biases experiment tracking (logs config, metrics, dataset/LoRA/GGUF artifacts).
- `--no-wandb`: Disable W&B even if enabled in config.
- `--export-gguf`: Automatically export to GGUF after training completes.

For the Workflow Assistant tool, `subjects/workflow_assistant.json` is a docs-backed audit artifact path. This subject is not intended for production Unity NPC export, and its dataset should be used for offline validation or tooling support only.

**W&B convenience preset:**
```bash
./ucore train subjects/my_npc.json --preset wandb
```
The `wandb` preset enables W&B tracking via config (equivalent to `--wandb`). Presets are single-select; use `--wandb` alongside another preset when needed:
```bash
./ucore train subjects/my_npc.json --preset fast-3b --wandb
```

### `export`
Converts a trained adapter to a GGUF model.
- `npc_key`: The NPC identifier.
- `--quantization`: Default `q4_k_m`.

### `export-adapter`
Exports **only** the LoRA weights (useful for `LLMUnity` side-loading).

---

## 🧪 Evaluation & Testing

### `smoke`
Rapidly tests a GGUF model for persona adherence.
- `--track`: Send results to Supabase.

### `evaluate`
Deep side-by-side comparison of two models.
- `--baseline`: Path to original GGUF.
- `--candidate`: Path to new GGUF.
- `--base-model`: Path to base model GGUF (required for LoRA adapter evaluation).
- `--wandb`: Log results to W&B — comparison table, per-category win rates, and report artifact.
- `--wandb-project`: W&B project name (default: `unsloth-core`).
- `--wandb-entity`: W&B entity (default: auto-detect from login).
- `--judge`: Use local Ollama LLM judge for scoring.
- `--report-html`: Generate HTML report with Chart.js visualizations.
- `--track`: Save results to `eval/results/eval_results.jsonl`.
- `--feedback-json`: Save structured per-concept eval results for the feedback loop.

### `compare-runs`
Compares two training runs using their specific `run_id`.

---

## 🛠️ Utility & Infrastructure

### `dashboard` (DEPRECATED)
> **Deprecated**: Use `npm run dev` in `frontend_control/unity-npc-llm-training-dashboard/` instead (port 3100).

Starts the legacy monitoring dashboard (default port 8000). Will be removed in a future release.

### `supabase-check`
Verifies that an NPC's profile and memory structures are correctly set up in the local Supabase instance.

### `deploy`
Copies exported GGUF files to the Unity project's `StreamingAssets` folder.
