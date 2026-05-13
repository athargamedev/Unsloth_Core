# Documentation Map: Unsloth_Core

This directory contains the detailed technical documentation for the Unsloth_Core project. Use this map to navigate the resources.

## 📂 Directory Structure

### 🏛️ Architecture & Core Concepts
- [PIPELINE_FLOW.md](architecture/PIPELINE_FLOW.md): Detailed breakdown of the 4-stage pipeline.
- [SUPABASE_SCHEMA.md](architecture/SUPABASE_SCHEMA.md): Database tables, functions, and memory retrieval logic.
- [NPC_LORA_WORKFLOW_ANALYSIS.md](NPC_LORA_WORKFLOW_ANALYSIS.md): Deep dive into LoRA adaptation for NPCs.

### 🛠️ Workflows
- [TRAINING_WORKFLOW.md](TRAINING_WORKFLOW.md): How to train a new model from scratch.
- [SUBJECT_SPEC_REVIEW_WORKFLOW.md](SUBJECT_SPEC_REVIEW_WORKFLOW.md): Checklist for reviewing `subjects/*.json` before generation/training.
- [NOTEBOOKLM_WORKFLOW.md](NOTEBOOKLM_WORKFLOW.md): Using NotebookLM for high-quality dataset generation.
- [OLLAMA_WORKFLOW.md](OLLAMA_WORKFLOW.md): Local-only generation and evaluation using Ollama.
- [EXPORT_WORKFLOW.md](EXPORT_WORKFLOW.md): Quantization and GGUF export for Unity.
- [EVALUATION_WORKFLOW.md](EVALUATION_WORKFLOW.md): Comparing models and tracking quality.

### 📚 Reference
- [CLI_REFERENCE.md](reference/CLI_REFERENCE.md): Full manual for the `./ucore` unified CLI.
- [SUBJECT_SPEC.md](reference/SUBJECT_SPEC.md): Schema definition for `subjects/*.json` files.
- [DATASET_CONTRACT_WORKFLOW.md](DATASET_CONTRACT_WORKFLOW.md): Specifications for ChatML and JSONL structures.
- [CONFIG_VALIDATION_WORKFLOW.md](CONFIG_VALIDATION_WORKFLOW.md): How training configurations are resolved.

### 🔗 Integrations
- [LLAMA_UNITY_PROFILE.md](LLAMA_UNITY_PROFILE.md): Setting up NPCs in the Unity game engine.
- [FRONTEND_DASHBOARD.md](integration/FRONTEND_DASHBOARD.md): Orchestration UI for pipeline management.
- [SUPABASE_INTEGRATION_CHECKLIST.md](SUPABASE_INTEGRATION_CHECKLIST.md): Verifying your local Supabase setup.

## 🚀 Getting Started
1. Start with the [README.md](../README.md) for the quick start guide.
2. Read [AGENTS.md](../AGENTS.md) if you are an AI assistant.
3. Consult the [TRAINING_WORKFLOW.md](TRAINING_WORKFLOW.md) for your first fine-tuning run.
