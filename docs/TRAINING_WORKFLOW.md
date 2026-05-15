# Training Pipeline Workflow

This document covers the end-to-end training pipeline using `scripts/train.py` — the unified launcher for fine-tuning NPC models with Unsloth. It supports subject specs, YAML configs, CLI overrides, and model-size-aware presets.

## 1. Overview

The training pipeline is a single entry point (`train.py`) that handles the full workflow:

1. **Config resolution** — loads a base YAML, applies a preset, then overlays CLI flags
2. **Dataset preparation** — auto-generates from a subject spec (`--from-spec`) or reads an existing JSONL
3. **Model setup** — loads a 4-bit quantized base model via Unsloth and attaches LoRA adapters
4. **SFT training** — runs supervised fine-tuning with packing, gradient accumulation, and early stopping
5. **Export (optional)** — saves a merged GGUF (`--export-gguf`) or a standalone LoRA adapter GGUF (`--export-lora`)

### Config Hierarchy

```
Base YAML (configs/lora-sft-base.yaml)
  ← Preset overrides (smoke, fast-1.7b, quality-1.7b, safe-any, etc.)
    ← CLI flags (--lr, --batch-size, --epochs, etc.)
```

Later sources override earlier ones. This means you can start from a sensible default and tweak exactly what you need.

## 2. Available Presets

Each preset is tuned for a specific model size and VRAM budget. Effective batch size = `batch_size * gradient_accumulation_steps`; target is ≥8 for stable convergence.

| Preset | Description | Batch | Grad Accum | Eff. Batch | Max Seq | LoRA r/α | VRAM |
|--------|-------------|-------|------------|------------|---------|----------|------|
| `smoke` | Quick smoke test (10 steps) | 1 | 2 | 2 | 512 | 8/16 | ~2 GB |
| `fast-0.5b` | Fast preset for 0.5B models | 8 | 2 | 16 | 2048 | 32/64 | ~4 GB |
| `fast-1.7b` | Fast preset for 1.7B models | 8 | 2 | 16 | 2048 | 32/64 | ~6 GB |
| `fast-3b` | Fast preset for 3B models | 1 | 8 | 8 | 2048 | 16/32 | ~6 GB |
| `quality-1.7b` | Quality preset for 1.7B, more epochs | 4 | 4 | 16 | 2048 | 32/64 | ~6 GB |
| `safe-any` | Safest preset for limited VRAM | 1 | 8 | 8 | 1024 | 8/16 | ~4 GB |

View available presets at any time:

```bash
python scripts/train.py --show-presets
```

## 3. Usage Examples

### Basic: Subject Spec + Preset

Generate a dataset from a subject spec and train with a preset:

```bash
python scripts/train.py subjects/chemistry_instructor.json --from-spec --preset fast-3b
```

This auto-generates the dataset to `subjects/datasets/chemistry_instructor/onyx/train.jsonl`, then trains with the `fast-3b` preset.

### YAML Config with Overrides

Use an existing config file and override specific values:

```bash
python scripts/train.py configs/lora-sft-base.yaml \
    --data subjects/datasets/chemistry_instructor/onyx/train.jsonl \
    --preset fast-1.7b
```

### Full Pipeline with Export

Generate, train, and export the LoRA adapter as GGUF in one command:

```bash
python scripts/train.py subjects/chemistry_instructor.json \
    --from-spec \
    --preset fast-3b \
    --export-lora
```

For a merged full-model GGUF instead:

```bash
python scripts/train.py subjects/chemistry_instructor.json \
    --from-spec \
    --preset fast-3b \
    --export-gguf \
    --quantization q4_k_m
```

### Dry Run

Print the resolved configuration without running training:

```bash
python scripts/train.py subjects/chemistry_instructor.json \
    --from-spec \
    --preset smoke \
    --dry-run
```

### Validate Effective Config (Phase 2)

Validate the resolved config and canonical path conventions before training:

```bash
./ucore validate-config --spec subjects/chemistry_instructor.json --preset fast-3b --data subjects/datasets/chemistry_instructor/onyx/train.jsonl --require-canonical --strict
```

Direct script mode:

```bash
python scripts/validate_config.py --spec subjects/chemistry_instructor.json --preset fast-3b --strict
```

### Direct CLI Mode (No Config File)

Train by specifying everything on the command line:

```bash
python scripts/train.py \
    --model unsloth/Qwen3-1.7B-bnb-4bit \
    --preset fast-1.7b \
    --data subjects/datasets/chemistry_instructor/onyx/train.jsonl \
    --output outputs/chemistry_instructor
```

### Post-Training Export

Export a previously trained model (adapter already in output dir):

```bash
python scripts/train.py configs/lora-sft-fast-3b.yaml --export-gguf
python scripts/train.py configs/lora-sft-fast-3b.yaml --export-lora
```

### Local vs Remote (Colab) Planning

Before launching expensive runs, compute deterministic placement:

```bash
./ucore plan-execution \
    --spec subjects/chemistry_instructor.json \
    --preset fast-3b
```

JSON mode for automation/pipelines:

```bash
./ucore plan-execution \
    --spec subjects/chemistry_instructor.json \
    --preset fast-3b \
    --json
```

This evaluates dataset-size and VRAM policy from `configs/workload-policy.yaml` and recommends:
- dataset generation location (`local` vs `remote`)
- training location (`local` vs `remote_colab`)

## 4. Flag Reference

| Flag | Short | Description |
|------|-------|-------------|
| `config_or_spec` | — | Path to YAML config or subject spec (with `--from-spec`) |
| `--from-spec` | — | Treat argument as a subject spec and auto-generate dataset |
| `--data` | `-d` | Training data path (JSONL or HF dataset) |
| `--val-data` | — | Validation data path (optional) |
| `--model` | `-m` | HuggingFace model ID |
| `--preset` | — | Training preset name (see table above) |
| `--output` | `-o` | Output directory for LoRA adapter |
| `--lr` | — | Learning rate |
| `--epochs` | — | Number of epochs |
| `--batch-size` | — | Per-device batch size |
| `--grad-accum` | — | Gradient accumulation steps |
| `--max-seq-len` | — | Max sequence length |
| `--lora-r` | — | LoRA rank |
| `--lora-alpha` | — | LoRA alpha |
| `--lora-dropout` | — | LoRA dropout |
| `--packing` | — | Enable packing (`True`/`False`) |
| `--train-on-responses` | — | Train on responses only (`True`/`False`) |
| `--export-gguf` | — | Export merged model to full GGUF after training |
| `--export-lora` | — | Export LoRA adapter as GGUF (for LLMUnity) |
| `--quantization` | — | GGUF quantization method (default: `q4_k_m`) |
| `--remote` | — | Generate remote training notebook (`colab`) |
| `--dry-run` | — | Print config and exit without training |
| `--show-presets` | — | Show available presets and exit |
| `--no-tensorboard` | — | Disable TensorBoard logging |

## 5. Output Structure

Training produces the following run-oriented directory layout:

```
outputs/{npc_key}/
├── latest -> runs/{run_id}       # Symlink to latest run
└── runs/
    └── {run_id}/
        ├── adapter_model.safetensors
        ├── adapter_config.json
        ├── tokenizer.json
        ├── tokenizer_config.json
        ├── config.yaml           # Frozen resolved config
        ├── metrics.json          # Core training metrics
        ├── run_manifest.json     # Reproducibility metadata (dataset hash, git commit, paths)
        └── runs/                 # TensorBoard event files
            └── events.out.tfevents.*
```

### Viewing Training Curves

Launch TensorBoard to monitor loss, learning rate, and gradient norms:

```bash
tensorboard --logdir outputs/chemistry_instructor/runs/
```

## 6. Troubleshooting

### CUDA Out of Memory (OOM)

| Symptom | Fix |
|---------|-----|
| CUDA OOM on model load | Use `--preset safe-any` (batch=1, seq_len=1024, r=8) |
| CUDA OOM mid-training | Lower batch size or sequence length manually: `--batch-size 1 --max-seq-len 1024` |
| CUDA OOM with 3B model | Switch to a 1.7B model and use `fast-1.7b` preset |

### Loss Not Decreasing

| Symptom | Fix |
|---------|-----|
| Loss flat or increasing | Lower learning rate: `--lr 1e-4` |
| Loss oscillating | Check `train_on_responses_only: true` (should be on by default) |
| Loss very high (5+) | Verify dataset is in ChatML format with proper role/content fields |

### Config Issues

| Symptom | Fix |
|---------|-----|
| "No config.yaml found" | Provide a config path, subject spec with `--from-spec`, or direct CLI args |
| Model not found | Ensure model ID ends with `-bnb-4bit` (Unsloth quantized format) |
| Dataset not loading | Verify JSONL messages conform to ChatML: `[{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]` |

### Model Format Requirements

All models **must** use the `-bnb-4bit` suffix from Unsloth's model repository:

```
unsloth/Llama-3.2-3B-Instruct-bnb-4bit    ✓
unsloth/Qwen3-1.7B-bnb-4bit                ✓
unsloth/Llama-3.1-8B-Instruct-bnb-4bit     ✓
unsloth/Llama-3.2-1B-Instruct-bnb-4bit     ✓
```
