# Documentation Map: Unsloth_Core

This directory contains the structured documentation for the Unsloth_Core project. Use this map to navigate.

## Directory Layout

```
docs/
├── MAP.md                                   ← (this file)
├── TRAINING_WORKFLOW_CONTEXT.md             ← End-to-end pipeline reference (primary AI-agent context)
├── architecture/
│   ├── PIPELINE_FLOW.md                     ← 7-stage pipeline: Spec → GGUF
│   ├── SUPABASE_SCHEMA.md                   ← Database: runtime tables + pipeline tables
│   ├── MODULAR_BACKEND.md                   ← Express backend architecture (27 files)
│   ├── AUTH_SYSTEM.md                       ← Bearer token auth with bcrypt and RBAC
│   ├── JOB_QUEUE.md                         ← PostgreSQL-backed job queue (FOR UPDATE SKIP LOCKED)
│   └── PIPELINE_DB.md                       ← Python-side DB integration (PipelineDB class)
├── integration/
│   └── FRONTEND_DASHBOARD.md                ← Orchestration UI for pipeline management
├── reference/
│   ├── CLI_REFERENCE.md                     ← Full `./ucore` command reference
│   └── SUBJECT_SPEC.md                      ← Schema definition for subjects/NPC_specs/*.json
└── plans/
    └── 2026-05-16-self-improving-pipeline.md ← Pipeline roadmap
```

## Document Quick Reference

| Document | What it covers |
|:---------|:---------------|
| [`TRAINING_WORKFLOW_CONTEXT.md`](TRAINING_WORKFLOW_CONTEXT.md) | Primary AI-agent context: full pipeline, presets, flags, data flow, evaluation patterns, common pitfalls |
| [`architecture/PIPELINE_FLOW.md`](architecture/PIPELINE_FLOW.md) | 7-stage pipeline flow: Generation → Sanitization → Dataset Quality Gate → Training → Export & Smoke Test → Model Evaluation → Feedback Loop |
| [`architecture/SUPABASE_SCHEMA.md`](architecture/SUPABASE_SCHEMA.md) | All database tables: runtime (npc_profiles, dialogue_sessions, npc_memories) and pipeline (jobs, runs, artifacts, quality gates, eval, configs, api_keys, audit_log) |
| [`architecture/MODULAR_BACKEND.md`](architecture/MODULAR_BACKEND.md) | 27-file modular Express backend: route map, middleware pipeline, design decisions |
| [`architecture/AUTH_SYSTEM.md`](architecture/AUTH_SYSTEM.md) | Bearer token auth: key format, bcrypt hashing, RBAC (admin/operator/viewer), audit logging, bootstrapping |
| [`architecture/JOB_QUEUE.md`](architecture/JOB_QUEUE.md) | PostgreSQL-backed job queue: FOR UPDATE SKIP LOCKED polling, PID tracking, exponential backoff, restart recovery |
| [`architecture/PIPELINE_DB.md`](architecture/PIPELINE_DB.md) | Python-side PipelineDB class: 20 methods, dual-mode (psycopg2 + REST API), auto-detection, column allowlist |
| [`integration/FRONTEND_DASHBOARD.md`](integration/FRONTEND_DASHBOARD.md) | React dashboard: modular backend, auth-protected APIs, job queue integration, Zustand + React Query state management |
| [`reference/CLI_REFERENCE.md`](reference/CLI_REFERENCE.md) | Full `./ucore` command reference with examples |
| [`reference/SUBJECT_SPEC.md`](reference/SUBJECT_SPEC.md) | JSON schema for `subjects/NPC_specs/*.json` — identity, teaching, dialogue, quest, refusal |
| [`plans/2026-05-16-self-improving-pipeline.md`](plans/2026-05-16-self-improving-pipeline.md) | Roadmap for feedback loop and knowledge gap detection |

## Getting Started

1. Start with the [README.md](../README.md) for the quick start guide and infrastructure overview.
2. Read [AGENTS.md](../AGENTS.md) if you are an AI assistant.
3. Read [TRAINING_WORKFLOW_CONTEXT.md](TRAINING_WORKFLOW_CONTEXT.md) for concise training-workflow context before making code or pipeline changes.
4. For new architecture additions, read [MODULAR_BACKEND.md](architecture/MODULAR_BACKEND.md) and [PIPELINE_DB.md](architecture/PIPELINE_DB.md) first.
5. Generate a dataset with `./ucore generate subjects/<npc>.json --technique docs`.
6. Train with `./ucore train subjects/<npc>.json --preset fast-3b --export-gguf`.
