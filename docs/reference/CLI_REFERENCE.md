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

### `generate`
Generates training data from a subject spec.
- `spec`: Path to JSON spec.
- `--technique`: `notebooklm` (default), `ollama`, `openai`, `anthropic`, `template`.
- `--ollama`: Shortcut for `--technique ollama`.

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
- `--from-spec`: Must be used when passing a `.json` subject file.
- `--preset`: Choose from `configs/presets/` (e.g., `smoke`, `fast-3b`, `quality-7b`).
- `--export-gguf`: Automatically export to GGUF after training completes.

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
- `--judge`: Use an LLM (via Ollama) to score the responses.

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
