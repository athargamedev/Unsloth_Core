---
name: unsloth-core-low-vram-training
description: Use when training, evaluating, benchmarking, or debugging Unsloth_Core on the local RTX 3060 6GB machine, especially when Ollama, llama.cpp, W&B, Triton, GCC, or VRAM pressure can affect success.
---

# Unsloth_Core Low-VRAM Training

Read `.codex/references/project-context.md` and `.codex/references/current-commands.md` before expensive train/eval work.

## Local Stance

Target host is RTX 3060-class with 6 GB VRAM. Treat VRAM as scarce. Do not run Ollama generation/judging, llama-server eval, and Unsloth training concurrently unless the user explicitly accepts the risk.

## Preflight

```bash
nvidia-smi
ollama ps
./ucore audit check
```

If Ollama holds VRAM, unload/stop the competing model and verify again before training or llama-server eval.

## Defaults

- Local judge/default: `qwen2.5:7b`.
- Production-ish local train preset: `fast-3b`, with preflight downgrade if the repo chooses it.
- LoRA defaults from strategy: r16, alpha32, batch size 1, grad accumulation 8, seq 512 for production profile.
- Use `PATH=/usr/bin:/bin:$PATH` around training when Triton/GCC toolchain resolution is suspect.

## Training

```bash
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json \
  --technique ollama --preset fast-3b --export-gguf
```

Do not claim W&B/Confident success unless output or artifacts prove it.

## Evaluation

Adapter GGUFs require base-model mode:

```bash
./ucore evaluate --baseline <baseline> --candidate <adapter.gguf> \
  --base-model <llama3.2_3b_base.gguf> \
  --spec data/npcs/specs/<npc>.json --report-html --judge --judge-model qwen2.5:7b
```

## Failure Rules

- CUDA OOM: unload Ollama, reduce concurrent work, use preflight-selected preset.
- llama-server timeout: inspect GPU and orphan ports before changing eval settings.
- DeepEval null-heavy output: inconclusive; inspect artifacts and rerun/debug judge.
- Export stalls on full merge: prefer adapter export plus base+LoRA evaluation.

## Done Evidence

Report concrete artifact paths: run dir, GGUF path, eval report, feedback JSON, and GPU/model checks used.

