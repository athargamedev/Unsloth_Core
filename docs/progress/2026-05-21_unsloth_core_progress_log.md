# Unsloth_Core Progress Log

Date: 2026-05-21
Scope: Unity NPC adapter training, dataset repair, eval readiness, and local inference/training reliability

## Executive summary
We completed a full repair cycle for the remaining local prototype NPCs and stabilized the 6GB training workflow on this machine. The main outcome is that both `chef_assistant` and `fitness_coach` were retrained on expanded, cleaned datasets and their adapter GGUFs are present in `exports/`. In parallel, we identified and documented the local Triton compiler bootstrap issue and the VRAM pressure pattern caused by background Ollama usage.

## What shipped
- Rebuilt and sanitized the Ollama datasets for:
  - `chef_assistant`
  - `fitness_coach`
- Retrained both NPCs successfully with W&B logging enabled.
- Confirmed adapter exports are available at:
  - `/home/athar/Projects/Unsloth_Core/exports/chef_assistant/chef_assistant-lora-f16.gguf`
  - `/home/athar/Projects/Unsloth_Core/exports/fitness_coach/fitness_coach-lora-f16.gguf`
- Captured the training reliability fix as a reusable skill:
  - `/home/athar/.hermes/skills/mlops-training/unsloth-core-6gb-training-repair/SKILL.md`

## Training results at a glance
- `chef_assistant`
  - Re-trained successfully on the expanded sanitized dataset (`123` kept examples).
  - Final run completed and exported the adapter.
  - W&B tracking was enabled for the run.
- `fitness_coach`
  - Re-trained successfully on the expanded sanitized dataset (`123` kept examples).
  - Final run completed and exported the adapter.
  - W&B tracking was enabled for the run.

## Reliability work completed
- Identified the low-level Triton bootstrap failure mode on this machine:
  - `CudaUtils` / compiler path issues
  - missing or inaccessible `gcc` / `as` in subprocess contexts
- Implemented a PATH-safe compiler wrapper:
  - `.toolchain/gcc-with-path.sh`
- Verified the wrapper resolves the compiler bootstrap path reliably.
- Confirmed that unloading Ollama (`qwen3:latest`) can recover enough VRAM for training.
- Standardized the low-VRAM fallback path:
  - `--preset safe-any`

## Operational notes
- Background Ollama processes can consume a large portion of the 6GB VRAM budget, so training should prefer a clean GPU whenever possible.
- The `safe-any` preset is the preferred fallback when the standard `fast-3b` preset is too aggressive for the current GPU state.
- Base-model paths with spaces can be brittle for llama.cpp-style subprocesses; no-space aliases are safer for repeated eval runs.

## What still needs follow-up
- Finish the updated final eval pass for the newly retrained adapters.
- Keep the eval pipeline on a no-space base-model alias and choose GPU layers that start quickly enough for this machine.
- Continue improving the investor-facing reporting/logging layer so progress is easy to review over time.

## References
- Repo instructions updated in `AGENTS.md`.
- Evaluation artifacts are written under `eval/reports/<npc_key>/`.
- Feedback JSON is written under `eval/results/feedback/<npc_key>_*.json`.
