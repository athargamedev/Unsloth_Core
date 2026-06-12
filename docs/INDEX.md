# Unsloth_Core Documentation

> **Documentation navigation hub.** Last verified: 2026-06-10.
> Each doc has a `last_verified` date. If stale, update from live repo/tool state, then bump the date.

Build GGUF LoRA adapters for llama3.2 3B NPCs. Unity/LLMUnity loads one shared base GGUF and swaps lightweight LoRA adapter GGUFs plus NPC system prompts.

---

## Getting Started

| Doc | Last verified | Purpose |
|-----|:------------:|---------|
| [`../AGENTS.md`](../AGENTS.md) | 2026-06-10 | **Primary entry point** — project context, hard rules, quickstart, canonical paths |
| [`./project-state.md`](project-state.md) | 2026-06-10 | Current NPC run state, process control, local services |
| [`./training-workflow.md`](training-workflow.md) | 2026-06-10 | Full pipeline detail — every stage with CLI commands |
| [`./platform-integration.md`](platform-integration.md) | 2026-06-10 | Platform roles, credentials, naming conventions |

## How-To Guides

| Doc | Purpose |
|-----|---------|
| [`./guides/operator-runbook.md`](guides/operator-runbook.md) | Quick human reference — canonical commands, output layout, debugging order |
| [`./guides/ollama-dataset-generator.md`](guides/ollama-dataset-generator.md) | Ollama generation setup, performance tuning, troubleshooting |
| [`./guides/deepeval-cheat-sheet.md`](guides/deepeval-cheat-sheet.md) | DeepEval 4.x metrics, config objects, env vars reference |

## Reference

| Doc | Purpose |
|-----|---------|
| [`./reference/cli-commands.md`](reference/cli-commands.md) | Every `./ucore` command, flag, and config key |
| [`./reference/subject-spec.md`](reference/subject-spec.md) | NPC spec JSON schema (`data/npcs/specs/*.json`) |
| [`./reference/agent-brief-template.md`](reference/agent-brief-template.md) | Template for creating new agent briefs |

## Integration Docs

| Doc | Purpose |
|-----|---------|
| [`./dlt_hub/README.md`](dlt_hub/README.md) | dltHub workspace — docs ingestion pipeline, MCP server, workspace tools |
| [`./integration/confident-ai-integration.md`](integration/confident-ai-integration.md) | Confident AI dataset management, goldens, classifier setup |
| [`./integration/frontend-dashboard.md`](integration/frontend-dashboard.md) | Dashboard architecture, API endpoints, job queue |
| [`./integration/llmunity-integration.md`](integration/llmunity-integration.md) | Unity/LLMUnity dual-GGUF strategy, folder structure |

## Historical / Background

| Doc | Last verified | Purpose |
|-----|:------------:|---------|
| [`./dataflow-report.md`](dataflow-report.md) | 2026-06-08 | Simplification progress report (historical record of what was cleaned) |
| [`./archive/`](archive/) | — | Deprecated plans, reports, and legacy references |

## Quick reference — canonical pipeline

```bash
source unsloth_env/bin/activate
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --mode fast
./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf
./ucore evaluate --baseline <baseline> --candidate <adapter> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

> **Target workflow (preferred for multi-stage runs):**
> ```
> ./ucore target plan --npc-key <npc> --technique ollama --profile npc-production-grounded --target-stage evaluate
> ./ucore target run --npc-key <npc> --technique ollama --profile npc-production-grounded --target-stage evaluate --resume
> ```
