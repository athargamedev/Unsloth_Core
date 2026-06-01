# Documentation Map: Unsloth_Core

This directory contains the structured documentation for the Unsloth_Core project. Use this map to navigate.

## Directory Layout

```text
docs/
├── index.md                              ← This map
├── project-state.md                      ← Canonical project state tracking
├── training-workflow.md                  ← End-to-end pipeline reference (AI context)
├── architecture/                         ← System diagrams and backend design docs
│   ├── auth-system.md
│   ├── job-queue.md
│   ├── modular-backend.md
│   ├── pipeline-db.md
│   ├── pipeline-flow.md
│   └── supabase-schema.md
├── guides/                               ← Runbooks, cheat sheets, and operation guides
│   ├── deepeval-cheat-sheet.md
│   ├── npc-training-evolution.md
│   ├── ollama-dataset-generator.md
│   ├── ollama-local-performance.md
│   └── operator-runbook.md
├── integration/                          ← End-user or UI integration docs
│   └── frontend-dashboard.md
├── planning/                             ← Past reviews and architecture plans
│   ├── code-review-report.md
│   ├── workflow-assistant-architecture.md
│   └── workflow-assistant-rag.md
├── reference/                            ← Schemas, CLI commands, and contracts
│   ├── cli-commands.md
│   ├── legacy-cli-reference.md
│   ├── npc-data-rl-execution-contract.md
│   ├── run-comparison-schema.md
│   └── subject-spec.md
└── visuals/                              ← Output graphs, HTML pipelines, and PDFs
    ├── 12-ai-visuals.pdf
    ├── legacy-dataflow-graph.html
    ├── npc-best-practices.html
    ├── npc-math-and-balancing.html
    ├── npc-pipeline-visuals.html
    └── workflow-dataflow-graph.html
```

## Document Quick Reference

| Document | What it covers |
|:---------|:---------------|
| [`training-workflow.md`](training-workflow.md) | Primary AI-agent context: full pipeline, presets, flags, data flow, evaluation patterns, common pitfalls |
| [`cli-commands.md`](reference/cli-commands.md) | Exhaustive, auto-verified `./ucore` command and flag reference |
| [`architecture/pipeline-flow.md`](architecture/pipeline-flow.md) | 7-stage pipeline flow: Generation → Sanitization → Dataset Quality Gate → Training → Export & Smoke Test → Model Evaluation → Feedback Loop |
| [`architecture/supabase-schema.md`](architecture/supabase-schema.md) | All database tables: runtime (npc_profiles, dialogue_sessions, npc_memories) and pipeline (jobs, runs, artifacts, quality gates, eval, configs, api_keys, audit_log) |
| [`architecture/modular-backend.md`](architecture/modular-backend.md) | 27-file modular Express backend: route map, middleware pipeline, design decisions |
| [`architecture/auth-system.md`](architecture/auth-system.md) | Bearer token auth: key format, bcrypt hashing, RBAC (admin/operator/viewer), audit logging, bootstrapping |
| [`architecture/job-queue.md`](architecture/job-queue.md) | PostgreSQL-backed job queue: FOR UPDATE SKIP LOCKED polling, PID tracking, exponential backoff, restart recovery |
| [`architecture/pipeline-db.md`](architecture/pipeline-db.md) | Python-side PipelineDB class: 20 methods, dual-mode (psycopg2 + REST API), auto-detection, column allowlist |
| [`integration/frontend-dashboard.md`](integration/frontend-dashboard.md) | React dashboard: modular backend, auth-protected APIs, job queue integration, Zustand + React Query state management |
| [`reference/legacy-cli-reference.md`](reference/legacy-cli-reference.md) | Full `./ucore` command reference with examples |
| [`reference/subject-spec.md`](reference/subject-spec.md) | JSON schema for `subjects/NPC_specs/*.json` — identity, teaching, dialogue, quest, refusal |

## Getting Started

1. Start with the [README.md](../README.md) for the quick start guide and infrastructure overview.
2. Read [AGENTS.md](../AGENTS.md) if you are an AI assistant.
3. Read [training-workflow.md](training-workflow.md) for concise training-workflow context before making code or pipeline changes.
4. For new architecture additions, read [modular-backend.md](architecture/modular-backend.md) and [pipeline-db.md](architecture/pipeline-db.md) first.
5. Generate a dataset with `./ucore generate subjects/<npc>.json --technique docs`.
6. Train with `./ucore train subjects/<npc>.json --preset fast-3b --export-gguf`.
