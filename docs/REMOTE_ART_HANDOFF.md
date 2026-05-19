# Remote ART Handoff: Colab Notebooks

Generated: 2026-05-17

This document explains how to run the Automated Retraining (ART) workflow
on Google Colab using the generated notebooks.

## Overview

ART runs a feedback loop that:
1. Loads evaluation feedback JSON
2. Identifies weak concepts
3. Regenerates targeted training data (Onyx + Ollama)
4. Retrains the LoRA adapter
5. Exports GGUF for Unity deployment

Since local GPU (RTX 3060 6GB) is insufficient for reliable training,
training moves to Colab (free T4 16GB).

## Generated Notebooks

### chef_assistant
- **File**: `colab/outputs/chef_assistant__fast-3b__remote_colab.ipynb`
- **State**: 0% win rate, 10/10 concepts weak
- **Goal**: Beat baseline (chef_assistant_v2-lora-f16.gguf)

### history_guide
- **File**: `colab/outputs/history_guide__fast-3b__remote_colab.ipynb`
- **State**: 40% win rate, improving
- **Goal**: Push win rate above 50%

## How to Run

### Step 1: Prepare Local Dataset (Run Locally)
The notebooks handle this, but you can also pre-generate locally:
```bash
# Already done — ChefAssistant Onyx dataset exists (113 train, 15 val)
# Already done — HistoryGuide Onyx dataset exists (113 train, 15 val)
```

### Step 2: Upload Notebook to Colab
1. Open https://colab.research.google.com/
2. File → Upload Notebook → select the `.ipynb` file
3. Runtime → Run all (or run cells sequentially)

### Step 3: Notebook Execution Flow
The notebook will:
1. Mount Google Drive for persistent storage
2. Clone the Unsloth_Core repo to Drive
3. Install Unsloth + dependencies
4. Install unsloth from pip (Colab has CUDA)
5. Run dataset sanitization
6. Run training with `--preset fast-3b --export-gguf`
7. Export GGUF adapter

### Step 4: Download Results
After training:
1. The GGUF file is in `exports/chef_assistant/` or `exports/history_guide/` inside the cloned repo
2. Download from Drive back to local machine
3. Run evaluation:
```bash
./ucore evaluate --base-model /path/to/base.gguf \
  --baseline exports/{npc_key}/{npc_key}_v2-lora-f16.gguf \
  --candidate exports/{npc_key}/{npc_key}-lora-f16.gguf \
  --spec subjects/NPC_specs/{npc_key}.json \
  --wandb \
  --feedback-json eval/results/feedback/{npc_key}_remote_v1.json
```

## Notes
- Colab runtime disconnects after ~12 hours of inactivity
- Keep the browser tab active during training
- If runtime disconnects: click the "Connect" button in the yellow disconnected banner at the top of the notebook
- Each training run takes ~20-40 minutes on T4 GPU
- W&B tracking works automatically (`wandb.init()` in training script)
- Download GGUF before closing the notebook

## ucore CLI: No `colab` Subcommand

The `ucore` CLI does **not** have a standalone `colab` command. Notebook generation
is integrated into the `plan-batch` subcommand via the `--generate-colab-notebooks`
flag. To regenerate notebooks in the future:

```bash
./ucore plan-batch \
  --spec subjects/NPC_specs/chef_assistant.json --spec subjects/NPC_specs/history_guide.json \
  --presets fast-3b \
  --generate-colab-notebooks \
  --colab-output-dir colab/outputs \
  --local-vram-gb 4.0
```

The `--local-vram-gb 4.0` override forces Colab routing (since 6GB local VRAM
technically meets the 5.2GB threshold for fast-3b but is unreliable in practice).

## Related Files
- `scripts/ops/colab_notebook_generator.py` — notebook generator
- `scripts/orchestration/plan_batch_execution.py` — batch planner
- `colab/art_plan.json` — full execution plan
