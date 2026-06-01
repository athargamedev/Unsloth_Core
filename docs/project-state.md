# Unsloth_Core Project State

Last verified: 2026-06-01

## Mission

Build GGUF LoRA adapters for llama3.2 3B NPCs. Unity/LLMUnity loads one shared base GGUF and swaps lightweight LoRA adapter GGUFs plus NPC system prompts. Local Supabase supports dialogue/session state.

## Active NPCs

Only these are active for prototype validation:

- `history_guide` — world history
- `chef_assistant` — culinary arts

If old docs mention other NPCs as active, treat that as deprecated unless the user explicitly reactivates them.

## Dataset generation policy

- Template generation is smoke/dev only.
- Never train production LoRA on template data.
- Production data must use the approved grounded workflow. User preference is NotebookLM CLI for production dataset creation.
- Current `./ucore generate` supports `docs`, `ollama`, `template`, `openai`, and `anthropic`; verify the intended production technique before training.
- NotebookLM rate-limit rule from user memory: use small chunks, about 10-12 asks per batch, with 10s+ delays; expect 30-60+ minute blocks after ~15-20 asks.

## Canonical pipeline

```bash
source unsloth_env/bin/activate
./ucore audit check
./ucore validate-spec subjects/NPC_specs/<npc>.json --generation-ready
# production: generate via NotebookLM/approved grounded path; template only for smoke
./ucore sanitize subjects/datasets/<npc>/<technique>/train.jsonl \
  --output subjects/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval subjects/NPC_specs/<npc>.json --technique <technique> --mode fast --judge-model qwen2.5:7b
./ucore train subjects/NPC_specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf
./ucore evaluate --baseline <base-or-baseline-gguf> --candidate <adapter-or-run> \
  --base-model <base-gguf> --spec subjects/NPC_specs/<npc>.json --report-html
```

## Quality gate

- Training expects `train_clean.jsonl`.
- Gate artifacts live beside the dataset:
  - `quality_summary.json`
  - `quality_failures.json`
- The training gate checks exact dataset hash, distribution gaps, unknown rows, sanitizer signals, and summary status.
- `--allow-ungated-dataset` is dev-only, not production.

## Canonical paths

- Specs: `subjects/NPC_specs/<npc>.json`
- Reference docs: `subjects/reference_docs/<npc>_primer.md`
- Datasets: `subjects/datasets/<npc>/<technique>/`
- Training runs: `outputs/<npc>/runs/<run_id>/`
- Pointers: `outputs/<npc>/best`, `outputs/<npc>/latest`
- GGUF adapters: `exports/<npc>/<npc>-lora-f16.gguf`
- Reports: `eval/reports/<npc>/`
- Feedback JSON: `eval/results/feedback/<npc>.json`
- Unity project: `~/Setup Guide In-Editor Tutorial/`
- Unity model folder: `Assets/StreamingAssets/Models/`

## Local services

- Supabase: start with `supabase start`
- Supabase DB: `15434`
- Supabase API/Kong: `16437`
- Supabase Studio: `16438`
- Dashboard package: `frontend_control/unity-npc-llm-training-dashboard/`
- Dashboard dev: `cd frontend_control/unity-npc-llm-training-dashboard && npm run dev`
- Dashboard port: `3100`

## Local machine constraints

- Local GPU is RTX 3060-class 6GB VRAM.
- Unload Ollama before train/eval if it holds VRAM.
- Local tested Ollama judge/default: `qwen2.5:7b`.
- Preflight may downgrade `fast-3b` to `safe-any` on low VRAM.
- Triton/Unsloth training may need `gcc` and `as` on PATH.

## Deprecated / avoid

- Do not describe `astronomy_guide` or `fitness_coach` as active.
- Do not present template datasets as production-ready.
- Do not use `qwen3:latest` as a confirmed local default unless re-verified.
- Do not treat adapter GGUFs as standalone full merged models; evaluate with base + LoRA when needed.
- Do not lower thresholds or delete rows to force a green gate.
- Do not claim W&B/Confident upload unless local output or URL proves it.
