---
last_verified: 2026-06-10
next_audit: 2026-07-10
---

# Unsloth_Core Project State

## Mission

Build GGUF LoRA adapters for llama3.2 3B NPCs. Unity/LLMUnity loads one shared base GGUF and swaps lightweight LoRA adapter GGUFs plus NPC system prompts. Local Supabase supports dialogue/session state.

## Active NPCs

- `history_guide` — world history (trained, loss 1.61)
- `chef_assistant` — culinary arts (trained, loss 1.22, eval reports)
- `marvel_heroes_instructor` — Agent Coulson (trained, loss 2.95, first run)

Deprecated: `astronomy_guide`, `fitness_coach`.

## Process control (new June 2026)

The local RTX 3060 6GB machine has three model-serving systems that compete for VRAM:

| System | Binary | Ports | Purpose |
|--------|--------|-------|---------|
| Cognee llama.cpp | `llama-server` | 18080 (chat), 18081 (embed) | Always-on LLM + embedding for Cognee |
| Ollama | `ollama serve` → `llama-server` | 11434 | `generate-ollama` dataset generation |
| Stale/orphan | `llama-server` | random | Left behind by training/eval pipeline runs |

**Unified manager:** `~/llama-servers.sh`

```
Commands:
  status      Show all model processes + VRAM
  start       Start Cognee's chat + embed servers
  stop        Stop Cognee's servers only
  killall     Kill ALL model processes (frees VRAM for training)
  preflight   Check ports, VRAM, orphan processes
  serve [model.gguf] [port]   Start a one-shot generation server (default: Qwen2.5-7B)

Workflow:
  # Before GPU training — free VRAM
  ~/llama-servers.sh killall

  # After training — restart Cognee
  ~/llama-servers.sh start

  # Or set and forget — cron watchdog auto-cleans orphans every 10 min
```

**Direct llama.cpp generation (`generate-local`):**

```
./ucore generate-local --model <gguf_path> data/npcs/specs/<npc>.json

# What it does:
#   1. Starts llama.cpp with tuned flags (gpu-layers 24, ctx-size 8192, batch 512, parallel 4)
#   2. Runs generation against OpenAI-compatible /v1/chat/completions endpoint
#   3. Stops the server when done (even on errors)

# Can also do manually:
#   ~/llama-servers.sh serve /path/to/model.gguf 18082
#   ./ucore generate-ollama --url http://127.0.0.1:18082/v1/chat/completions
#   pkill -f "llama-server.*port 18082"
```

The Ollama ↔ OpenAI compatibility layer detects `/v1/` in the URL automatically:
- `--url http://localhost:11434/api/chat` → Ollama format (`api/chat`, `format: "json"`, `message.content`)
- `--url http://127.0.0.1:18082/v1/chat/completions` → OpenAI format (`/v1/chat/completions`, `response_format`, `choices[0].message.content`)

## Current verified run state

Verified 2026-06-09:

- **history_guide**: promoted run `20260607_fast-1.7b_llama3.2-3b_002` (loss 1.61). No eval reports yet (blocked by missing base GGUF download).
- **chef_assistant**: latest/best `20260608_safe-any_llama3.2-3b_003` (loss 1.22). Full eval reports at `artifacts/eval/reports/chef_assistant/`. Runtime eval: 5/10 wins (50%).
- **marvel_heroes_instructor**: promoted run `20260609_safe-any_llama3.2-3b_003` (loss 2.95). Dataset: 150 Ollama-generated rows (guardrail min_words relaxed to 15). GGUF adapter at `artifacts/exports/marvel_heroes_instructor/` (24.3 MB). Report bundle at `artifacts/reports/marvel_heroes_instructor/`.

## Dataset generation policy

- Template generation is smoke/dev only.
- Never train production LoRA on template data.
- Production data must use the approved grounded workflow (Ollama or direct llama.cpp).
- **Use `./ucore generate-ollama`** for Ollama-based generation.
- **Use `./ucore generate-local --model <gguf>`** for direct llama.cpp generation (more GPU control).
- `./ucore generate --technique ollama` is deprecated (hits legacy path).
- Feedback loop: `./ucore feedback --auto` uses `generate-ollama --concept-focus` + `sanitize` + `dataset-eval`.
- Top-level compatibility imports removed. Use canonical subpackages.

## Canonical workflow

Primary agent/operator path:

```bash
source unsloth_env/bin/activate
./ucore target plan --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate
./ucore target run --npc-key <npc> --technique ollama \
  --profile npc-production-grounded --target-stage evaluate --resume
```

Manual recovery:

```bash
source unsloth_env/bin/activate
~/llama-servers.sh killall                     # free VRAM
./ucore audit check
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready

# Generation (pick one):
# Option A — Ollama:
./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
# Option B — Direct llama.cpp:
./ucore generate-local --model <gguf_path> data/npcs/specs/<npc>.json --fresh

./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --mode fast
./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf
./ucore evaluate --baseline <base-or-baseline-gguf> --candidate <adapter-or-run> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

### Scripts location

All pipeline scripts live in `src/core/` (organized by function: `dataset/`, `training/`, `evaluation/`, `export/`, `ops/`). The old `scripts/` was a symlink to `src/core/` — removed to eliminate confusion. Use `./ucore` to run all pipeline commands.

### CLI structure

The CLI (`src/cli/ucore`) currently exposes 31 top-level commands. The canonical pipeline uses only 6:

1. `validate-spec` → 2. `generate-ollama` or `generate-local` → 3. `sanitize` → 4. `dataset-eval` → 5. `train` (+ `--export-gguf`) → 6. `evaluate`

Dead/deprecated commands are marked `[LEGACY]`, `[DEPRECATED]`, or `[EXPERIMENTAL]` in help text.

## Quality gate

- Training expects `train_clean.jsonl`.
- Gate artifacts: `quality_summary.json`, `quality_failures.json`.
- Gate checks: dataset hash, distribution gaps, unknown rows, sanitizer signals, summary status.
- `--allow-ungated-dataset` is dev-only, not production.
- DeepEval fast-mode failures are diagnostic only (structural/sanitizer failures still block).

## Canonical paths

- Specs: `data/npcs/specs/<npc>.json`
- Reference docs: `data/npcs/reference_docs/<npc>_primer.md`
- Datasets: `data/datasets/<npc>/<technique>/`
- Training runs: `artifacts/models/<npc>/runs/<run_id>/`
- Pointers: `artifacts/models/<npc>/best`, `artifacts/models/<npc>/latest`
- GGUF adapters: `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- Reports: `artifacts/eval/reports/<npc>/`
- Feedback JSON: `artifacts/eval/results/feedback/<npc>.json`
- Unity project: `~/Setup Guide In-Editor Tutorial/`
- Unity model folder: `Assets/StreamingAssets/Models/`
- Process manager: `~/llama-servers.sh`
- Watchdog script: `~/.hermes/scripts/stale-llama-server-clean.sh` (auto-run every 10min)

## Local services

- Supabase: check with `python src/core/ops/docker_core_status.py`.
- Current Docker core project: `LLM_WSL`.
- Current local ports:
  - Supabase DB: `15433`
  - Supabase API/Kong: `16433`
  - Supabase Studio: `16434`
  - Supabase Analytics: `16435`
  - Supabase Inbucket: `16436`
- Dashboard: `src/dashboard/unity-npc-llm-training-dashboard/`, dev at `npm run dev`, port `3100`.
- Cognee chat server: `127.0.0.1:18080`
- Cognee embed server: `127.0.0.1:18081`

## Local machine constraints

- GPU: RTX 3060-class, 6GB VRAM.
- **Before GPU work:** `~/llama-servers.sh killall` to free VRAM from stale processes.
- Preflight may downgrade `fast-3b` to `safe-any` on low VRAM.
- Default judge: `qwen2.5:7b` via Ollama.
- Available models: Qwen2.5-7B cached in Ollama blobs, nomic-embed GGUF cached.
- Base GGUF for evaluation (Llama-3.2-3B-Instruct Q2_K) not downloaded yet — HF CDN too slow.
- Triton/Unsloth training may need `gcc` and `as` on PATH.

## Deprecated / avoid

- Do not describe `astronomy_guide` or `fitness_coach` as active.
- Do not present template datasets as production-ready.
- Do not treat adapter GGUFs as standalone full merged models; evaluate with base + LoRA.
- Do not lower thresholds or delete rows to force a green gate.
- Do not claim W&B/Confident upload unless local output or URL proves it.

## Remaining work

- Download base GGUF for evaluation (Llama-3.2-3B-Instruct) — try HF mirror or alternative source.
- Run full eval for history_guide (blocked by base GGUF).
- Lower marvel_heroes_instructor training loss (2.95 is high — need more data or better data quality).
- Walk through SETUP.md from fresh clone.
- Investigate GPU OOM during eval — partial offload with `--gpu-layers < 99` to fit base + LoRA on 6GB.
