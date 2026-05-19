# Remote 3B Quality Training Handoff

Goal: keep Unity runtime on the fast Llama 3.2 3B base, but train better 3B-compatible LoRA adapters on Colab.

## What changed

- Archived stale 8B experiment artifacts and old removed-NPC reports under `archive/`.
- Increased active NPC dataset distribution in both specs:
  - identity: 12
  - teaching: 56
  - dialogue: 32
  - quest: 16
  - refusal: 16
- Applied feedback-loop focus from the current 3B evals:
  - boosted identity, teaching, dialogue during generation
- Regenerated larger Onyx datasets:
  - history_guide: 205 train + 27 validation
  - chef_assistant: 205 train + 27 validation
- Fixed dataset concept extraction so portfolio/eval metadata no longer fills with noisy concepts like `and causes`, `should know`, `the printing`.
- Added remote quality preset:
  - `configs/presets/remote-3b-quality.yaml`
- Generated Colab notebooks:
  - `colab/outputs/history_guide__remote-3b-quality__remote_colab.ipynb`
  - `colab/outputs/chef_assistant__remote-3b-quality__remote_colab.ipynb`
- Generated batch plan:
  - `colab/remote3b_quality_plan.json`

## Correct runtime target

Use this base in Unity:

`Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf`

The new Colab notebooks train this model family:

`unsloth/Llama-3.2-3B-Instruct-bnb-4bit`

So the exported LoRA GGUFs are compatible with the existing fast 3B Unity runtime.

## Colab run steps

1. Open Colab.
2. Upload one notebook:
   - `colab/outputs/history_guide__remote-3b-quality__remote_colab.ipynb`
   - or `colab/outputs/chef_assistant__remote-3b-quality__remote_colab.ipynb`
3. Runtime → Change runtime type → GPU.
4. Run all cells.
5. In the Hugging Face auth cell, paste a token if gated-model access fails.
6. Download the exported LoRA GGUF from the final notebook cell.
7. Put it in:
   - `/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/`
8. Evaluate it locally against the current 3B LoRA.

## Preset details

`remote-3b-quality` uses:

- base model: Llama 3.2 3B Instruct 4-bit
- epochs: 5
- batch size: 4
- gradient accumulation: 4
- effective batch: 16
- LoRA rank: 64
- LoRA alpha: 128
- dropout: 0.05
- W&B enabled with tags:
  - remote-3b-quality
  - portfolio
  - onyx-feedback

## After downloading Colab GGUFs

Run comparison against current local 3B LoRA, not the 8B artifacts:

```bash
./ucore evaluate \
  --baseline exports/history_guide/history_guide-lora-f16.gguf \
  --candidate exports/history_guide/<downloaded-new-history-3b-lora>.gguf \
  --base-model "/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf" \
  --spec subjects/NPC_specs/history_guide.json \
  --num-questions 10 \
  --report-html --track --wandb \
  --feedback-json eval/results/feedback/history_guide_remote3b_quality_feedback.json
```

Repeat for `chef_assistant`.
