# Run Comparison Schema

## 1. Purpose

The `eval/results/run_comparison_table.json` file is the single source of truth for every NPC LoRA training run. It exists to:

- **Automate preset selection** — Compare loss, eval metrics, and training speed across presets (`safe-any`, `fast-1.7b`, etc.) to pick the best configuration for each model+NPc combo.
- **Compare by model and parameters** — Directly compare `llama3.2 3B` vs `qwen3 1.7B` runs side by side to understand trade-offs (loss quality vs. training speed vs. VRAM usage).
- **Track promotion candidates** — Identify which runs have the best eval metrics and could be promoted to production (the `promoted` boolean).
- **Preserve experiment history** — Keep a permanent record of every run including what changed (technique, preset, dataset size) so we never lose context on what worked and what didn't.

## 2. Schema Field Documentation

### Top-Level

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Semver for the schema itself. Bump when adding/removing fields. |
| `created` | string (ISO date) | When this file was created. |
| `description` | string | Human-readable description of the file's purpose. |
| `runs` | array[Run] | Ordered list of training runs (newest first recommended). |

### Run Object

#### `run_id`
- **Type:** `string`
- **Format:** `{YYYYMMDD}_{preset}_{model-short}_{###}`
- **Example:** `20260529_fast-1.7b_qwen3-1.7b-unsloth_002`
- **Uniqueness:** MUST be globally unique across all runs.

#### `npc_key`
- **Type:** `string`
- **Description:** Snake_case NPC identifier matching the spec filename.
- **Examples:** `history_guide`, `chef_assistant`

#### `timestamp`
- **Type:** `string` (ISO date)
- **Description:** Calendar date the training was started.

#### `model`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Full HuggingFace model path (e.g. `unsloth/Llama-3.2-3B-Instruct-bnb-4bit`). |
| `params` | string | Human-readable parameter count (e.g. `3B`, `1.7B`). |
| `architecture` | string | Model architecture family (e.g. `llama3.2`, `qwen3`). |
| `base_gguf_available` | bool | Whether a base GGUF exists in Unity's `StreamingAssets` for runtime loading. |

#### `preset`

| Field | Type | Description |
|-------|------|-------------|
|| `name` | string | Preset name from `etc/presets/` (e.g. `safe-any`, `fast-1.7b`, `smoke`). |
| `lora_r` | int | LoRA rank dimension. |
| `lora_alpha` | int | LoRA alpha scaling factor. |
| `max_seq_length` | int | Maximum sequence length in tokens. |
| `grad_accum` | int | Gradient accumulation steps. |
| `batch_size` | int | Per-device batch size. |

#### `dataset`

| Field | Type | Description |
|-------|------|-------------|
| `technique` | string | Generation technique (`template`, `ollama`, `docs`, `openai`, `anthropic`). |
| `num_examples` | int | Number of training examples in the sanitized dataset. |
| `categories_passed` | bool | Whether all 5 categories met minimum example counts. |
| `quality_gate_pass_rate` | float or null | DeepEval quality gate pass rate (null if not run). |

#### `train_on_responses_only`
- **Type:** `bool`
- **Description:** Whether the `train_on_responses_only` flag was active. When `false`, the model trained on full chat sequences including the user prompt, which may inflate loss numbers.

#### `results`

| Field | Type | Description |
|-------|------|-------------|
| `training_loss` | float | Final training loss from the trainer. |
| `eval_loss` | float or null | Eval loss from a held-out validation split (null if not run). |
| `win_rate` | float or null | Side-by-side eval win rate against a baseline (null if not evaluated). |
| `num_eval_questions` | int or null | Number of evaluation questions used (null if not evaluated). |
| `avg_quality` | float or null | Average quality score from eval (null if not rated). |
| `smoke_test_pass` | bool | Whether the smoke test (persona adherence) passed. |

#### `export`

| Field | Type | Description |
|-------|------|-------------|
| `mode` | string | Export mode: `adapter` (LoRA GGUF only) or `full-merge` (merged GGUF). |
| `size_mb` | int | File size in MB. |
| `path` | string | Relative path to the exported GGUF file. |
| `has_gguf` | bool | Whether the GGUF file exists on disk. |

#### `resources`

| Field | Type | Description |
|-------|------|-------------|
| `vram_gb` | float | Peak VRAM usage in GB during training. |
| `training_time_sec` | float or null | Total training wall-clock time in seconds (null if not recorded). |
| `samples_per_sec` | float or null | Training throughput in samples per second (null if not recorded). |

#### `promoted`
- **Type:** `bool`
- **Description:** Whether this run was promoted to production use. Only the best-performing run per NPC should be `true`.

#### `notes`
- **Type:** `string`
- **Description:** Free-text notes explaining the run context, anomalies, bugs, or decisions.

## 3. How to Query

### Compare presets for the same model

```python
python3 -c "
import json
data = json.load(open('eval/results/run_comparison_table.json'))
for r in data['runs']:
    if 'history_guide' in r['npc_key']:
        print(f'{r[\"model\"][\"architecture\"]:10s} | {r[\"preset\"][\"name\"]:10s} | loss {r[\"results\"][\"training_loss\"]:.3f} | eval {str(r[\"results\"][\"eval_loss\"]):6s} | win {str(r[\"results\"][\"win_rate\"]):5s}')
"
```

### Find the best run for each NPC

```python
python3 -c "
import json
data = json.load(open('eval/results/run_comparison_table.json'))
bests = {}
for r in data['runs']:
    key = r['npc_key']
    loss = r['results']['training_loss']
    if key not in bests or loss < bests[key]['results']['training_loss']:
        bests[key] = r
for npc, r in bests.items():
    print(f'{npc:20s} | loss {r[\"results\"][\"training_loss\"]:.3f} | {r[\"model\"][\"architecture\"]:8s} | {r[\"preset\"][\"name\"]:10s} | {r[\"dataset\"][\"technique\"]:8s}')
"
```

### Compare training speed by preset

```python
python3 -c "
import json
data = json.load(open('eval/results/run_comparison_table.json'))
for r in data['runs']:
    if r['resources']['training_time_sec']:
        print(f'{r[\"run_id\"]:45s} | {r[\"preset\"][\"name\"]:10s} | {r[\"resources\"][\"training_time_sec\"]:6.1f}s | {str(r[\"resources\"][\"samples_per_sec\"]):5s} | loss {r[\"results\"][\"training_loss\"]:.3f}')
"
```

### Find runs with eval data

```python
python3 -c "
import json
data = json.load(open('eval/results/run_comparison_table.json'))
for r in data['runs']:
    if r['results']['eval_loss'] is not None or r['results']['win_rate'] is not None:
        print(f'{r[\"run_id\"]:45s} | eval_loss={str(r[\"results\"][\"eval_loss\"]):7s} | win_rate={str(r[\"results\"][\"win_rate\"]):5s}')
"
```

### List all unique NPC-model combinations

```python
python3 -c "
import json
data = json.load(open('eval/results/run_comparison_table.json'))
seen = set()
for r in data['runs']:
    combo = (r['npc_key'], r['model']['architecture'], r['model']['params'])
    if combo not in seen:
        seen.add(combo)
        print(f'{combo[0]:20s} | {combo[1]:8s} | {combo[2]:4s}')
"
```

## 4. How to Add a New Run

After a training run completes, append a new entry to the `runs` array. Use this template:

```json
{
  "run_id": "{YYYYMMDD}_{preset}_{model-short}_{###}",
  "npc_key": "npc_name",
  "timestamp": "YYYY-MM-DD",
  "model": {
    "name": "unsloth/Model-Name-bnb-4bit",
    "params": "1.7B",
    "architecture": "qwen3",
    "base_gguf_available": false
  },
  "preset": {
    "name": "fast-1.7b",
    "lora_r": 16,
    "lora_alpha": 32,
    "max_seq_length": 2048,
    "grad_accum": 4,
    "batch_size": 2
  },
  "dataset": {
    "technique": "template",
    "num_examples": 72,
    "categories_passed": true,
    "quality_gate_pass_rate": null
  },
  "train_on_responses_only": false,
  "results": {
    "training_loss": 0.000,
    "eval_loss": null,
    "win_rate": null,
    "num_eval_questions": null,
    "avg_quality": null,
    "smoke_test_pass": true
  },
  "export": {
    "mode": "adapter",
    "size_mb": 7,
    "path": "exports/{npc_key}/{npc_key}-lora-f16.gguf",
    "has_gguf": true
  },
  "resources": {
    "vram_gb": 4.20,
    "training_time_sec": null,
    "samples_per_sec": null
  },
  "promoted": false,
  "notes": "Describe what this run tested, any bugs, anomalies, or key decisions."
}
```

**Steps:**
1. Copy the template into `eval/results/run_comparison_table.json` as a new entry in the `runs` array.
2. Assign a unique `run_id` following the convention `{YYYYMMDD}_{preset}_{model-key}_{###}`.
3. Fill in all known fields. Use `null` for unknown/unavailable metrics rather than omitting them.
4. Validate the JSON: `python3 -c "import json; json.load(open('eval/results/run_comparison_table.json')); print('Valid')"`
5. After eval completes, update `results.win_rate`, `results.eval_loss`, and `promoted` accordingly.

## 5. Automation Ideas

### Preset Selection Heuristic

Rank presets by a composite score for each (npc, model) pair:

```
composite_score = w1 * (1 - normalized_training_loss)
                + w2 * win_rate
                + w3 * (1 / normalized_training_time)
                + w4 * (1 - normalized_eval_loss)
```

Weights can be tuned per use case (e.g., prioritize quality over speed for production). The run table provides all the raw data to compute this.

### Sweep Optimization

When running hyperparameter sweeps:
1. Generate candidate configs from `--preset` variations.
2. After each run, append results to this table.
3. Use the table to identify diminishing returns: does increasing `lora_r` beyond 16 still improve loss for this model size?
4. Feed the best row into the next iteration's preset config via `etc/presets/`.

### Automatic Promotion Gate

A CI check (or post-training hook) could:
1. Read the best existing run for this NPC from the table.
2. Compare new run's `training_loss` and `win_rate` against the best.
3. If new run surpasses best by >5% in both metrics, set `promoted: true` and un-promote the old best.
4. Flag for human review if metrics are close (<5% difference).

### Training Budget Forecasting

Aggregate `resources.training_time_sec` and `resources.vram_gb` by (model, preset) to:
- Predict training cost before launching.
- Automatically select the cheapest preset that meets a minimum loss threshold.
- Flag runs that exceed expected VRAM for their model class.
