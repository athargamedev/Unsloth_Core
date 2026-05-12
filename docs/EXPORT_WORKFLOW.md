# GGUF Export & Deployment Workflow

This document covers two export paths for trained LoRA adapters — full model merging via `scripts/export.py` and lightweight LoRA-only adapter export via `scripts/export_adapter.py` — plus deployment to Unity via `scripts/deploy_to_unity.py`.

## 1. Overview

After training a LoRA adapter, you need to export it for inference. There are two approaches:

| Path | Script | Output | Use Case |
|------|--------|--------|----------|
| **Full GGUF Merge** | `export.py` | Merged model + LoRA → single GGUF | Standalone inference, llama.cpp |
| **LoRA Adapter GGUF** | `export_adapter.py` | LoRA adapter only (small GGUF) | Runtime loading in LLMUnity |

### Naming Convention

All exports follow this naming pattern:

```
{npc_key}-{model_short}-{quant}.gguf
```

Examples:
- `chemistry_instructor-llama3.2-3b-q4_k_m.gguf`
- `chemistry_instructor-llama3.2-3b-f16.gguf`
- `bible_instructor-qwen3-1.7b-f16.gguf`

The `model_short` is derived automatically (e.g., `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` → `llama3.2-3b`).

## 2. Full GGUF Export (export.py)

The `export.py` script merges the trained LoRA adapter with its base model and exports a standalone GGUF file suitable for llama.cpp and other GGUF-compatible runtimes.

### Usage

```bash
# Recommended: NPC key + model ID
python scripts/export.py chemistry_instructor \
    --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit

# Legacy: point to training output directory
python scripts/export.py outputs/chemistry_instructor/ \
    --quantization q4_k_m

# Export only the quantized variant (skip f16)
python scripts/export.py chemistry_instructor \
    --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit \
    --skip-f16

# Custom output directory
python scripts/export.py chemistry_instructor \
    --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit \
    --output-dir /custom/path
```

### Output

```
exports/{npc_key}/
├── {npc_key}-{model_short}-q4_k_m.gguf    # Quantized (default)
├── {npc_key}-{model_short}-f16.gguf        # Full-precision variant
└── manifest.json
```

By default, both `q4_k_m` (quantized) and `f16` (full-precision) variants are generated. Use `--skip-f16` to skip the f16 variant.

## 3. LoRA Adapter Export (export_adapter.py)

The `export_adapter.py` script converts a PEFT LoRA adapter directory (containing `adapter_model.safetensors` and `adapter_config.json`) into a standalone GGUF-format LoRA adapter. This is much smaller than a full merge and can be loaded at runtime by LLMUnity.

### Usage

```bash
# Single adapter
python scripts/export_adapter.py outputs/bible_instructor

# With custom output type
python scripts/export_adapter.py outputs/marvel_instructor --outtype q8_0

# Batch convert all adapters in outputs/
python scripts/export_adapter.py --all

# Explicit output file path
python scripts/export_adapter.py outputs/chemistry_instructor \
    --outfile /custom/path/my_adapter.gguf
```

### Output Format

The output is saved alongside the adapter directory by default:

```
outputs/{npc_key}/
├── adapter_model.safetensors     # Original PEFT weights
├── adapter_config.json            # Original PEFT config
├── {npc_key}-lora.{outtype}.gguf  # Converted GGUF LoRA
└── ...
```

### Flag Reference

| Flag | Description |
|------|-------------|
| `adapter_path` | Path to PEFT adapter directory |
| `--all` | Convert all adapters in `outputs/` |
| `--outtype` | Output format: `f32`, `f16`, `bf16`, `q8_0`, `auto` (default: `f16`) |
| `--outfile` | Explicit output file path |
| `--base` | Path to directory with clean `config.json` (auto-detected if omitted) |

### Quantization Reference

| Outtype | Size vs f16 | Quality | Use Case |
|---------|-------------|---------|----------|
| `f16` | 1× (baseline) | Full precision | Default for LLMUnity runtime loading |
| `q8_0` | ~50% | Near-lossless | Smaller adapter, minimal quality loss |
| `f32` | 2× | Full precision | Debugging, maximum compatibility |

## 4. Deploy to Unity (deploy_to_unity.py)

The `deploy_to_unity.py` script automates the full deployment pipeline: scanning exports, optionally running `export_adapter.py`, copying GGUF files to a Unity project, and writing a deployment manifest.

### Usage

```bash
# Auto-detect Unity project (sibling directory)
python scripts/deploy_to_unity.py

# Specify Unity project path explicitly
python scripts/deploy_to_unity.py --unity-project /path/to/UnityProject

# Dry run (show what would happen)
python scripts/deploy_to_unity.py --dry-run

# Export GGUF only (no Unity copy)
python scripts/deploy_to_unity.py --export-only

# Skip export step (only copy already-exported files)
python scripts/deploy_to_unity.py --skip-export
```

### Deployment Pipeline

The script does three things:

1. **Scans** `exports/{npc_key}/` for GGUF files and their corresponding subject specs
2. **Copies** GGUF files to `UnityProject/Assets/StreamingAssets/Models/`
3. **Writes** a deployment manifest (`npc_deployment_manifest.json`) consumed by Unity Editor's NPCDeploymentImporter

### Manifest Format

```json
{
  "version": 1,
  "generated_at": "2026-05-12T10:30:00+00:00",
  "source": "Unsloth_Core",
  "npcs": [
    {
      "npc_key": "chemistry_instructor",
      "lora_gguf": "Models/chemistry_instructor-llama3.2-3b-q4_k_m.gguf",
      "npc_name": "ChemistryInstructor",
      "system_prompt": "You are ChemistryInstructor...",
      "subject": "General chemistry"
    }
  ]
}
```

## 5. Output Structure Summary

```
exports/{npc_key}/
├── {npc_key}-{model_short}-q4_k_m.gguf     # Quantized GGUF (~2-4 GB for 3B)
├── {npc_key}-{model_short}-f16.gguf         # Full-precision GGUF (~6 GB for 3B)
└── manifest.json                             # Export metadata
```

## 6. Troubleshooting

### Converter Not Found

```
Error: convert_lora_to_gguf.py not found locally.
```

The script searches several locations:

- `~/.unsloth/llama.cpp/convert_lora_to_gguf.py`
- `~/.unsloth/llama.cpp/convert/convert_lora_to_gguf.py`
- `~/llama.cpp/convert_lora_to_gguf.py`
- System PATH

If not found, it attempts to download from the llama.cpp GitHub repo. Install llama.cpp or ensure the converter is available.

### Adapter Config Not Found

```
Error: outputs/chemistry_instructor does not contain adapter_config.json
```

Train the adapter first:

```bash
python scripts/train.py subjects/chemistry_instructor.json --from-spec --preset fast-3b
```

### GGUF Merge Failed

If the merged GGUF file is unexpectedly small or missing:

1. Check that the output directory contains `adapter_model.safetensors` and `adapter_config.json`
2. Ensure the base model ID matches the one used during training
3. Try with `--skip-f16` to narrow down which variant fails

### Unity Project Not Found

```
[deploy] Warning: Specified path doesn't look like a Unity project
```

The auto-detect looks for a sibling directory named `Setup Guide In-Editor Tutorial` with an `Assets/` subdirectory. Provide an explicit path:

```bash
python scripts/deploy_to_unity.py --unity-project /absolute/path/to/UnityProject
```
