# Unsloth_Core

A professional, "agent-first" pipeline for building NPC dialogue models with Unsloth, exporting GGUF for Unity, and tracking results in Supabase.

## 🚀 Quick Start

1. **Activate Environment**
   ```bash
   source unsloth_env/bin/activate
   ```

2. **Run the Full Pipeline**
   ```bash
   ./ucore pipeline subjects/chemistry_instructor.json --preset fast-3b
   ```

3. **Deploy to Unity**
   ```bash
   ./ucore deploy --unity-project /path/to/my_game
   ```

---

## 📂 Project Structure

- `ucore`: The unified CLI entry point.
- `subjects/`: NPC identity and knowledge specifications (.json).
- `subjects/datasets/`: Generated training and validation data (.jsonl).
- `subjects/schemas/`: JSON Schema validators for training data format.
- `subjects/reference_docs/`: Reference materials for NotebookLM dataset generation.
- `scripts/`: Core Python implementation of the 4-stage pipeline.
- `configs/`: YAML presets for different hardware and model targets.
- `outputs/`: LoRA adapters and training logs.
- `exports/`: Quantized GGUF models ready for Unity.

---

## 📖 Documentation

The project documentation is structured for both human developers and AI agents:

- **[AGENTS.md](AGENTS.md)**: Primary reference for AI models (Start here if you are an agent).
- **[docs/MAP.md](docs/MAP.md)**: Central index of all technical documentation.

### Key References
- [Architecture: Pipeline Flow](docs/architecture/PIPELINE_FLOW.md)
- [Architecture: Supabase Schema](docs/architecture/SUPABASE_SCHEMA.md)
- [Reference: CLI Manual (ucore)](docs/reference/CLI_REFERENCE.md)
- [Reference: Subject Spec Schema](docs/reference/SUBJECT_SPEC.md)

---

## 🛠️ Unified CLI (`ucore`)

```bash
./ucore generate subjects/workflow_assistant.json --technique docs
./ucore generate subjects/subject.json --technique template
./ucore sanitize subjects/datasets/subject/template/train.jsonl --strict-canonical
./ucore dataset-eval subjects/subject.json --technique template --judge-model qwen2.5:7b
./ucore train subjects/subject.json --preset fast-3b
./ucore smoke exports/subject/model.gguf
./ucore evaluate --baseline old.gguf --candidate new.gguf
./ucore feedback eval/results/feedback/subject.json --dry-run
```

### Local Dataset Quality Loop

DeepEval is the local build-loop gate before training:

1. **Validate generation readiness** from the spec, reference doc, and dataset counts.
2. **Generate** a canonical dataset under `subjects/datasets/{npc}/{technique}/`.
3. **Sanitize** to `train_clean.jsonl` with complete metadata.
4. **Dataset-eval** with local Ollama `qwen2.5:7b`.
5. **Fix generation** from `quality_failures.json`, then rerun before training.

```bash
./ucore validate-spec subjects/history_guide.json --generation-ready
./ucore generate subjects/history_guide.json --technique template
./ucore sanitize subjects/datasets/history_guide/template/train.jsonl \
  --output subjects/datasets/history_guide/template/train_clean.jsonl \
  --strict-canonical \
  --require-complete-metadata
./ucore dataset-eval subjects/history_guide.json --technique template --soft-fail
```

Outputs:
- `subjects/datasets/{npc}/{technique}/quality_summary.json`
- `subjects/datasets/{npc}/{technique}/quality_failures.json`

Generation contract:
- `docs/NPC_DATA_RL_EXECUTION_CONTRACT.md`

### Self-Improving Model Feedback Loop

The model feedback loop closes the gap between trained model evaluation and dataset generation:

1. **Generate** datasets with canonical local techniques (`template`, `docs`, `ollama`, `openai`, `anthropic`)
2. **Evaluate** with structured output (`--feedback-json`)
3. **Feedback** auto-detects weak concepts, classifies as training density vs knowledge gaps, and triggers targeted regeneration

```bash
# Full loop
./ucore evaluate --baseline old.gguf --candidate new.gguf --spec subjects/npc.json --feedback-json eval/results/feedback/npc.json
./ucore feedback eval/results/feedback/npc.json --auto
# Then retrain and re-evaluate to measure improvement

# One-shot auto-retrain (CI mode):
./ucore feedback eval/results/feedback/npc.json --auto --auto-retrain --baseline old.gguf --train-preset fast-3b
# Chains: regenerate → sanitize → train → evaluate → pipeline state

# Machine-readable output for dashboards:
./ucore feedback eval/results/feedback/npc.json --json --skip-gap-detection
```

### Workflow Assistant tool
The Workflow Assistant is a dedicated local tool for mastering Unsloth_Core, not a Unity NPC dataset. It lives in `workflow_assistant/` and uses local Onyx retrieval to ground the frontend assistant in indexed repo docs and workflow sources.

For offline artifact generation and corpus auditing, the legacy docs-backed workflow assistant path remains available:

```bash
./ucore validate-spec subjects/workflow_assistant.json
./ucore generate subjects/workflow_assistant.json --technique docs
./ucore sanitize subjects/datasets/workflow_assistant/docs/train.jsonl --strict-canonical
./ucore validate-config --spec subjects/workflow_assistant.json --preset smoke --data subjects/datasets/workflow_assistant/docs/train_clean.jsonl --require-canonical
```

This path is for audit and tooling support only; `workflow_assistant` is not intended for Unity model export.

Its safe corpus manifest lives at `docs/corpora/workflow_assistant_docs.json`.

For a full list of commands, see the [CLI Reference](docs/reference/CLI_REFERENCE.md).

---

## ⚖️ License
MIT. See [LICENSE](LICENSE) for details.
