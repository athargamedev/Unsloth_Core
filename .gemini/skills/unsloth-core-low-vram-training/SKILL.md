# Unsloth_Core Low-VRAM Training

Use when training, evaluating, or benchmarking Unsloth_Core on the local RTX 3060 6GB machine.

## Local Hardware Constraints

- **GPU:** RTX 3060 Laptop (6GB VRAM).
- **Scarce Resource:** VRAM is limited. Unload Ollama models before starting training or heavy evaluation.
- **Check GPU:** Use `nvidia-smi` and `ollama ps` to verify memory usage.

## Preflight Checks

Run before expensive stages:

```bash
source unsloth_env/bin/activate
# Check if current spec/preset fits in VRAM
python scripts/ops/preflight.py --phase train --preset fast-3b --spec data/npcs/specs/<npc>.json --json
```

## Known-Good Defaults

- **Train Preset:** `fast-3b` (auto-downgrades to `safe-any` via preflight if needed).
- **LoRA Config:** rank 16, alpha 32, dropout 0.05.
- **Batching:** batch size 1, grad accumulation 8, max sequence length 2048, packing enabled.
- **Judge Model:** `qwen2.5:7b` (stable JSON behavior).

## Training Pattern

```bash
# Ensure GCC/Triton can find tools
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json \
  --technique <technique> --preset fast-3b --export-gguf
```

## Evaluation Pattern

Adapter GGUFs MUST be evaluated with the base model:

```bash
./ucore evaluate \
  --baseline <baseline_adapter_or_base.gguf> \
  --candidate artifacts/exports/<npc>/<npc>-lora-f16.gguf \
  --base-model <base_gguf_path> \
  --spec data/npcs/specs/<npc>.json \
  --report-html --judge --judge-model qwen2.5:7b
```

## Troubleshooting

- **CUDA OOM:** Unload Ollama, check `nvidia-smi`, use `safe-any` preset.
- **Triton/GCC Errors:** Ensure `/usr/bin/gcc` is in PATH.
- **Timeout:** Verify `nvidia-smi`, ensure no other models are holding VRAM.
