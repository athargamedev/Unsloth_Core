# Evaluation & Comparison Workflow

This document covers three evaluation modes: side-by-side model comparison, training metrics extraction, and interactive chat — all via `scripts/evaluate.py`, with additional helpers for quick local eval and result tracking.

## 1. Overview

The evaluation pipeline measures how well a fine-tuned NPC model performs against a baseline or against its own training data. Three primary modes:

| Mode | Command | Purpose |
|------|---------|---------|
| **Side-by-side** | `--baseline` + `--candidate` | Compare two GGUF models on held-out questions |
| **Training metrics** | `--training-metrics` | Extract loss curves from TensorBoard logs |
| **Interactive chat** | `--interactive --model` | Manually test a model via llama.cpp server |

### Evaluation Metrics

Each response is scored on:

- **Sentence count** — checks the ≤3 sentence constraint
- **Name presence** — verifies the NPC name appears in the response
- **AI disclaimer** — detects phrases like "I am an AI"
- **Diversity (TTR)** — type-token ratio for lexical variety
- **Quality estimate** — perplexity-based heuristic (lower = better)
- **Think tags** — detects unwanted `response` tags

## 2. Side-by-Side Comparison

Compares a baseline model against a candidate model using questions from a subject spec's validation set.

### Usage

```bash
python scripts/evaluate.py \
    --baseline exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-f16.gguf \
    --candidate exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-q4_k_m.gguf \
    --spec subjects/chemistry_instructor.json
```

### With LLM Judge

Use an Ollama-powered judge to score responses:

```bash
python scripts/evaluate.py \
    --baseline baseline.gguf \
    --candidate candidate.gguf \
    --spec subjects/chemistry_instructor.json \
    --judge \
    --judge-model llama3.1:latest
```

### Custom Validation Data

Override the validation set:

```bash
python scripts/evaluate.py \
    --baseline baseline.gguf \
    --candidate candidate.gguf \
    --val-data datasets/chemistry_instructor/ollama/validation.jsonl \
    --num-questions 25
```

### Generate HTML Report

```bash
python scripts/evaluate.py \
    --candidate exports/chemistry_instructor/*.gguf \
    --spec subjects/chemistry_instructor.json \
    --output eval_report.md
```

The report is saved as a Markdown file with aggregate metrics, per-question comparisons, constraint violation tracking, and winner tallies.

### Output

```
eval/reports/{npc_key}/
└── eval_{date}.md

eval/comparisons/
└── {npc_key}_vs_{baseline}_{date}.md
```

## 3. Training Metrics Extraction

Extract training loss, validation loss, and perplexity from TensorBoard event files.

### Usage

```bash
# From an NPC's training runs
python scripts/evaluate.py --training-metrics --npc-key chemistry_instructor

# From a custom runs directory
python scripts/evaluate.py --training-metrics outputs/chemistry_instructor/runs/
```

### Output

Metrics are printed to stdout in this format:

```
============================================================
  TRAINING METRICS
============================================================

  Run: run_20260512_103000
    train/loss:
      steps:    150
      final:    0.4231
      best:     0.3812
      perplex:  1.53
    eval/loss:
      steps:    6
      final:    0.5123
      best:     0.4901
      perplex:  1.67
```

## 4. Interactive Chat

Launch an interactive session with a GGUF model via llama.cpp server for manual testing.

### Usage

```bash
# Basic interactive mode
python scripts/evaluate.py --interactive --model exports/chemistry_instructor/*.gguf

# Custom port
python scripts/evaluate.py --interactive --model model.gguf --port 9999
```

### Sample Session

```
> What is an atom?
An atom is the basic building block of matter. Think of it as a tiny solar system with a nucleus at the center and electrons orbiting around it.

  [len=18 | 1.2s | ttr=78.9% | qual=3.4]

> Tell me about chemical bonds.
Chemical bonds are the forces that hold atoms together. They're like magnets — opposite charges attract and create stable molecules.

  [len=16 | 0.9s | ttr=81.2% | qual=2.8]
```

Output includes token count, latency, type-token ratio, and quality score per response.

## 5. Quick Local Evaluation (quick_eval.py)

For a faster evaluation that doesn't require starting a llama.cpp server (uses `llama-cpp-python` directly):

```bash
python scripts/quick_eval.py outputs/chemistry_instructor/ \
    --samples 50

# With subject spec
python scripts/quick_eval.py outputs/chemistry_instructor/ \
    --spec subjects/chemistry_instructor.json \
    --val-data datasets/chemistry_instructor/notebooklm/validation.jsonl
```

Measures token overlap (Jaccard similarity) between generated and expected responses, plus diversity, sentence count, and AI disclaimer detection.

## 6. Tracking Results (track_eval_results.py)

Store evaluation results locally or in Supabase for historical tracking:

```bash
# Save a result
python scripts/track_eval_results.py \
    --track \
    --npc-key chemistry_instructor \
    --model outputs/chemistry_instructor/chemistry_instructor-lora.f16.gguf \
    --win-rate 0.75 \
    --avg-quality 42.5 \
    --notes "First training run - good constraint compliance"

# View history
python scripts/track_eval_results.py --show
python scripts/track_eval_results.py --show --npc-key chemistry_instructor
```

Results are stored locally in `eval_results.jsonl` and optionally synced to the Supabase `test_results` table.

## 7. Output Structure Summary

```
eval/
├── training-metrics/
│   └── {npc_key}.yaml            # Extracted training metrics
├── reports/
│   └── {npc_key}/
│       └── eval_{date}.md         # Side-by-side evaluation report
├── comparisons/
│   └── {npc_key}_vs_{baseline}_{date}.md  # Comparison report
└── results/
    └── eval_results.jsonl         # Tracked evaluation results
```

## 8. Troubleshooting

### llama-server Not Found

```
Warning: llama-server not found. Install it or provide the path.
```

The script searches for `llama-server` in these locations:

- Alongside the GGUF file
- `~/.unsloth/llama.cpp/build/bin/llama-server`
- `$PATH`

Install via Unsloth's llama.cpp build or ensure the binary is on your PATH.

### No Validation Set Found

```
No validation set found. Using generic evaluation questions.
```

The script looks for validation data at `datasets/{npc_key}/{technique}/validation.jsonl`. Generate a dataset first:

```bash
python scripts/generate_dataset.py subjects/chemistry_instructor.json
```

### Judge Model Unavailable

- Ensure Ollama is running: `ollama serve`
- Pull the judge model: `ollama pull llama3.1:latest`
- Verify the Ollama API is accessible at `http://localhost:11434`

### TensorBoard Not Installed

```bash
pip install tensorboard
```

### High Loss / Poor Scores

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Low token overlap | Model doesn't reproduce validation answers | Train longer or increase LoRA rank |
| High AI disclaimer rate | Model not following system prompt | Enable `--train-on-responses` with proper ChatML formatting |
| Very short responses | Sentence constraint too tight | Check system prompt max sentence rule |
