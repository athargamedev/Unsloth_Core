# Documentation Map: Unsloth_Core

This directory contains the structured documentation for the Unsloth_Core project. Use this map to navigate.

## 📂 Directory Layout

```
docs/
├── MAP.md                              ← (this file)
├── ONYX_WORKFLOW.md                    ← Onyx RAG setup, indexing, dataset generation
├── TRAINING_WORKFLOW_CONTEXT.md        ← End-to-end pipeline reference (primary AI-agent context)
├── architecture/
│   ├── PIPELINE_FLOW.md                ← 4-stage pipeline: Spec → GGUF
│   └── SUPABASE_SCHEMA.md              ← Database tables, functions, memory retrieval
├── integration/
│   └── FRONTEND_DASHBOARD.md           ← Orchestration UI for pipeline management
├── reference/
│   ├── CLI_REFERENCE.md                ← Full `./ucore` command reference
│   └── SUBJECT_SPEC.md                 ← Schema definition for subjects/NPC_specs/*.json
└── plans/
    └── 2026-05-16-self-improving-pipeline.md  ← Pipeline roadmap
```

## 📖 Document Quick Reference

| Document | What it covers |
|:---------|:---------------|
| [`ONYX_WORKFLOW.md`](ONYX_WORKFLOW.md) | Onyx RAG generation v2 — indexing documents, running Onyx queries, natural conversation templates, variant selection |
| [`TRAINING_WORKFLOW_CONTEXT.md`](TRAINING_WORKFLOW_CONTEXT.md) | Primary AI-agent context: full pipeline, presets, flags, data flow, evaluation patterns, common pitfalls |
| [`architecture/PIPELINE_FLOW.md`](architecture/PIPELINE_FLOW.md) | 4-stage pipeline flow: Generation → Sanitization → Training → Export & Validation |
| [`architecture/SUPABASE_SCHEMA.md`](architecture/SUPABASE_SCHEMA.md) | Local Supabase schema: npc_profiles, dialogue_sessions, npc_memories, test_results |
| [`integration/FRONTEND_DASHBOARD.md`](integration/FRONTEND_DASHBOARD.md) | React dashboard: pipeline orchestration, job table, realtime metrics |
| [`reference/CLI_REFERENCE.md`](reference/CLI_REFERENCE.md) | Full `./ucore` command reference with examples |
| [`reference/SUBJECT_SPEC.md`](reference/SUBJECT_SPEC.md) | JSON schema for `subjects/NPC_specs/*.json` — identity, teaching, dialogue, quest, refusal |
| [`plans/2026-05-16-self-improving-pipeline.md`](plans/2026-05-16-self-improving-pipeline.md) | Roadmap for feedback loop, Onyx-driven self-improvement, and knowledge gap detection |

## 🚀 Getting Started

1. Start with the [README.md](../README.md) for the quick start guide.
2. Read [AGENTS.md](../AGENTS.md) if you are an AI assistant.
3. Read [TRAINING_WORKFLOW_CONTEXT.md](TRAINING_WORKFLOW_CONTEXT.md) for concise training-workflow context before making code or pipeline changes.
4. Set up Onyx with [ONYX_WORKFLOW.md](ONYX_WORKFLOW.md), then index your NPC reference documents.
5. Generate a dataset with `./ucore generate subjects/<npc>.json --technique onyx`.
6. Train with `./ucore train subjects/<npc>.json --preset fast-3b --export-gguf`.
