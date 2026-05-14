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
- `datasets/`: Generated training and validation data (.jsonl).
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
./ucore generate subjects/subject.json --technique notebooklm
./ucore sanitize datasets/subject/notebooklm/train.jsonl
./ucore train subjects/subject.json --preset fast-3b
./ucore smoke exports/subject/model.gguf
./ucore evaluate --baseline old.gguf --candidate new.gguf
```

### Workflow Assistant path

The frontend Workflow Assistant has a dedicated docs-backed dataset path:

```bash
./ucore validate-spec subjects/workflow_assistant.json
./ucore generate subjects/workflow_assistant.json --technique docs
./ucore sanitize datasets/workflow_assistant/docs/train.jsonl --strict-canonical
./ucore validate-config --spec subjects/workflow_assistant.json --preset smoke --data datasets/workflow_assistant/docs/train_clean.jsonl --require-canonical
```

Its safe corpus manifest lives at `docs/corpora/workflow_assistant_docs.json`.

For a full list of commands, see the [CLI Reference](docs/reference/CLI_REFERENCE.md).

---

## ⚖️ License
MIT. See [LICENSE](LICENSE) for details.
