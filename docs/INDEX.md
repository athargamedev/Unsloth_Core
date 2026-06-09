---
last_verified: 2026-06-05
---

# Documentation Map: Unsloth_Core

This directory contains the structured documentation for the Unsloth_Core project. Use this map to navigate.

## Directory Layout

```text
docs/
├── INDEX.md                               ← This map
├── project-state.md                       ← Canonical project state tracking
├── training-workflow.md                   ← End-to-end pipeline reference (AI context)
├── architecture/                          ← System diagrams and backend design docs
│   ├── auth-system.md
│   ├── job-queue.md
│   ├── modular-backend.md
│   ├── pipeline-db.md
│   ├── pipeline-flow.md
│   └── supabase-schema.md
├── guides/                                ← Runbooks, cheat sheets, and operation guides
│   ├── deepeval-cheat-sheet.md
│   ├── npc-training-evolution.md
│   ├── ollama-dataset-generator.md
│   ├── ollama-local-performance.md
│   └── operator-runbook.md
├── integration/                           ← End-user or UI integration docs
│   └── frontend-dashboard.md
├── planning/                              ← Past reviews and architecture plans
│   ├── code-review-report.md
│   ├── workflow-assistant-architecture.md
│   └── workflow-assistant-rag.md
├── reference/                             ← Schemas, CLI commands, and contracts
│   ├── agent-brief-template.md            ← Standard template for all Hermes/Codex agent briefs
│   ├── cli-commands.md
│   ├── legacy-cli-reference.md
│   ├── npc-data-rl-execution-contract.md
│   ├── run-comparison-schema.md
│   └── subject-spec.md
└── visuals/                               ← Output graphs, HTML pipelines, and PDFs
    ├── 12-ai-visuals.pdf
    ├── legacy-dataflow-graph.html
    ├── npc-best-practices.html
    ├── npc-math-and-balancing.html
    ├── npc-pipeline-visuals.html
    └── workflow-dataflow-graph.html
```

## Document Quick Reference

| Document | What it covers | Last verified |
|:---------|:---------------|:--------------|
| [`training-workflow.md`](training-workflow.md) | Primary AI-agent context: full pipeline, presets, flags, data flow, evaluation patterns, common pitfalls | 2026-06-01 |
| [`platform-integration.md`](platform-integration.md) | Platform roles (Ollama, W&B, Confident AI, HuggingFace, Modal, llama.cpp): what runs work vs logs results, credential requirements, naming conventions, decision matrix | 2026-06-09 |
| [`cli-commands.md`](reference/cli-commands.md) | Exhaustive, auto-verified `./ucore` command and flag reference | 2026-06-01 |
| [`architecture/pipeline-flow.md`](architecture/pipeline-flow.md) | 7-stage pipeline flow: Generation → Sanitization → Dataset Quality Gate → Training → Export & Smoke Test → Model Evaluation → Feedback Loop | 2026-06-01 |
| [`architecture/supabase-schema.md`](architecture/supabase-schema.md) | All database tables: runtime (npc_profiles, dialogue_sessions, npc_memories) and pipeline (jobs, runs, artifacts, quality gates, eval, configs, api_keys, audit_log) | 2026-06-01 |
| [`architecture/modular-backend.md`](architecture/modular-backend.md) | 27-file modular Express backend: route map, middleware pipeline, design decisions | 2026-06-01 |
| [`architecture/auth-system.md`](architecture/auth-system.md) | Bearer token auth: key format, bcrypt hashing, RBAC (admin/operator/viewer), audit logging, bootstrapping | 2026-06-01 |
| [`architecture/job-queue.md`](architecture/job-queue.md) | PostgreSQL-backed job queue: FOR UPDATE SKIP LOCKED polling, PID tracking, exponential backoff, restart recovery | 2026-06-01 |
| [`architecture/pipeline-db.md`](architecture/pipeline-db.md) | Python-side PipelineDB class: 20 methods, dual-mode (psycopg2 + REST API), auto-detection, column allowlist | 2026-06-01 |
| [`integration/frontend-dashboard.md`](integration/frontend-dashboard.md) | React dashboard: modular backend, auth-protected APIs, job queue integration, Zustand + React Query state management | 2026-06-01 |
| [`reference/agent-brief-template.md`](reference/agent-brief-template.md) | Standard template for all Hermes/Codex agent briefs | 2026-06-05 |
| [`reference/legacy-cli-reference.md`](reference/legacy-cli-reference.md) | Full `./ucore` command reference with examples | 2026-06-01 |
| [`reference/subject-spec.md`](reference/subject-spec.md) | JSON schema for `data/npcs/specs/*.json` — identity, teaching, dialogue, quest, refusal | 2026-06-01 |

## Getting Started

1. Start with the [README.md](../README.md) for the quick start guide and infrastructure overview.
2. Read [AGENTS.md](../AGENTS.md) if you are an AI assistant.
3. Read [training-workflow.md](training-workflow.md) for concise training-workflow context before making code or pipeline changes.
4. For new architecture additions, read [modular-backend.md](architecture/modular-backend.md) and [pipeline-db.md](architecture/pipeline-db.md) first.
5. [CONTRIBUTING.md](../CONTRIBUTING.md) — how to contribute, PR process, agent context guidelines.
6. [SETUP.md](../SETUP.md) — full dev environment setup.
7. Generate a dataset with `./ucore generate data/npcs/specs/<npc>.json --technique docs`.
8. Train with `./ucore train data/npcs/specs/<npc>.json --preset fast-3b --export-gguf`.
