# Ollama-Driven NPC Dataset Generation & Training Workflow

This document outlines the enhanced pipeline for generating high-quality, synthetic NPC training data using local LLMs (via Ollama) and fine-tuning them using the Unsloth framework.

### See Also

- [NotebookLM Dataset Generation](NOTEBOOKLM_WORKFLOW.md) — Cloud-based, research-grounded dataset generation via NotebookLM API
- [Training Pipeline](TRAINING_WORKFLOW.md) — End-to-end training with presets, config hierarchy, and LoRA fine-tuning
- [GGUF Export & Deployment](EXPORT_WORKFLOW.md) — Exporting trained adapters and deploying to Unity
- [Evaluation & Comparison](EVALUATION_WORKFLOW.md) — Side-by-side eval, training metrics, and interactive chat

## 1. Overview

The "Ollama Workflow" replaces traditional, rigid template-based data generation with an AI-driven approach. By using a local LLM (e.g., `llama3.1`) to simulate both user queries and NPC responses, we produce training data that is more diverse, persona-consistent, and capable of multi-turn conversation.

## 2. The Pipeline Architecture

The workflow consists of three primary stages:

### Stage A: Concept Extraction
The script `scripts/generate_dataset.py` extracts "seeds" for the LLM from:
1.  **The Subject String**: Key terms from the high-level subject description.
2.  **Research Queries**: Keywords extracted from the `research_queries` array in the `subject.json` specification. This ensures the model covers specific technical or thematic topics defined for that NPC.

### Stage B: Synthetic Generation (via Ollama)
For each NPC category (Identity, Teaching, Dialogue, Quest, Refusal), the system:
- **Injects NPC Rules**: The full system prompt is provided to Ollama to ensure the generated responses follow character constraints (sentence length, tone, analogies).
- **JSON Mode**: Uses Ollama's native `format="json"` to guarantee valid training data structures.
- **Multi-Turn Logic**: Generates 2-3 turn dialogue chains (default 40% of the dataset) to train conversational continuity.
- **Chain-of-Thought**: Instructs the LLM to provide a `"thought"` field explaining why the response adheres to the persona rules.

### Stage C: Fine-Tuning (via Unsloth)
The generated `.jsonl` files are fed into `scripts/train.py`, which:
- Uses **LoRA (Low-Rank Adaptation)** for efficient 4-bit training.
- Applies **Model-Size Presets** (`fast-1.7b`, `safe-any`) to optimize for available VRAM.
- Exports a standalone **GGUF LoRA Adapter** for seamless integration with Unity/LLMUnity.

---

## 3. Usage Guide

### Step 1: Generate the Dataset
To generate a new dataset using Ollama:
```bash
# Using the --technique flag (recommended)
python scripts/generate_dataset.py subjects/chemistry_instructor.json --technique ollama --multi-turn-ratio 0.4

# Using the --ollama flag (legacy, still supported)
python scripts/generate_dataset.py subjects/chemistry_instructor.json --ollama --multi-turn-ratio 0.4
```
**Key Flags:**
- `--technique ollama`: Sets the generation technique to Ollama (writes to `subjects/datasets/{npc_key}/ollama/`).
- `--ollama`: Legacy flag to enable LLM generation (requires Ollama running locally).
- `--multi-turn-ratio`: Percentage of the dataset that will be multi-turn conversations (0.0 to 1.0).
- `--temperature`: Controls the diversity of the generated responses.

### Step 2: Clean the Dataset (Auto-Sanitization)
The system includes a sanitization step to ensure all message content is formatted as strings, preventing `pyarrow` errors during training. This is handled automatically by the generation script.

### Step 3: Run Training
Fine-tune the model on the new dataset:
```bash
python scripts/train.py --data subjects/datasets/chemistry_instructor/ollama/train.jsonl --preset fast-1.7b --export-lora
```
**Key Presets:**
- `fast-1.7b`: Recommended for 1.7B - 3B models on 6GB VRAM.
- `safe-any`: Use this if you encounter CUDA Out-of-Memory (OOM) errors.

### Step 4: Evaluate & Compare
Compare the new model against a baseline or old version:
```bash
python scripts/evaluate.py --baseline <old_model>.gguf --candidate <new_model>.gguf --judge --spec subjects/chemistry_instructor.json
```

---

## 4. Why This is Better

| Feature | Template System (Old) | Ollama System (New) |
| :--- | :--- | :--- |
| **User Interaction** | Predictable, repetitive queries. | Realistic, "messy" human questions. |
| **Persona Depth** | Fixed responses. | Creative analogies and varied tone. |
| **Continuity** | Single-turn only. | **Multi-turn dialogue chains.** |
| **Topical Coverage** | Limited to subject name. | **Deep coverage via research queries.** |

## 5. Technical Requirements

- **Ollama**: Must be running with the target model (default `llama3.1:latest`).
- **Unsloth**: Python environment with `unsloth`, `torch`, and `transformers` installed.
- **GPU**: 6GB+ VRAM recommended for training; 8GB+ for simultaneous generation and training.
