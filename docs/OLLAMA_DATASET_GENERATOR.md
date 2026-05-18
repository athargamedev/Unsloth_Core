# Ollama Dataset Generator (generate_dataset_ollama.py)

High-performance, Ollama-optimized NPC dataset generator for Unsloth_Core. Designed for fast, reliable local LLM-based generation with advanced retry logic, progress tracking, and Ollama health checks.

## Quick Start

### Basic Usage
```bash
# Generate dataset for history_guide with default Ollama model (llama2)
./ucore generate-ollama subjects/history_guide.json

# With custom model
./ucore generate-ollama subjects/chemistry_instructor.json --model llama3.1

# Dry-run: see generation plan without generating
./ucore generate-ollama subjects/fitness_coach.json --dry-run

# With health check and auto-pull model
./ucore generate-ollama subjects/astronomy_guide.json --check-health --pull-model --model mistral
```

### Direct Script Usage
```bash
python scripts/generate_dataset_ollama.py subjects/history_guide.json
python scripts/generate_dataset_ollama.py subjects/history_guide.json --model llama3.1 --batch-size 2
```

## Features

### 🎯 Core Capabilities
- **Local Ollama Integration**: Works with any Ollama-compatible model
- **Advanced Retry Logic**: Exponential backoff, automatic retry on timeout/failure
- **Concurrent Generation**: Configurable batch size for parallelized generation
- **Context Grounding**: Leverages reference docs for more accurate responses
- **Progress Tracking**: Real-time ETA, success rates, error logging

### 🔍 Health & Reliability
- **Ollama Health Check**: Verify service is running before generation
- **Model Auto-Pull**: Automatically pull missing models from Ollama registry
- **Error Tracking**: Detailed error logs saved to `generation_errors.json`
- **Retry Strategy**: Configurable max retries with intelligent backoff

### 📊 Generation Control
- **Temperature Control**: Adjust output creativity (0.0 = deterministic, 1.0 = creative)
- **Batch Size**: Control parallelization (default 4, reduce for low-memory systems)
- **Dry-Run Mode**: Preview generation plan without generating
- **Concept Focus**: (Coming) Boost specific categories

## Command Line Reference

### Arguments

#### Required
- `spec`: Path to subject spec JSON (e.g., `subjects/history_guide.json`)

#### Optional - Model Selection
- `--model MODEL`: Ollama model name (default: `llama2`)
  - Common options: `llama2`, `llama3.1`, `mistral`, `neural-chat`, `qwen`
  - Use `ollama list` to see available models
  
- `--url URL`: Ollama server URL (default: `http://localhost:11434`)
  - For remote servers: `http://192.168.1.100:11434`

#### Optional - Generation Control
- `--temperature TEMP`: Generation temperature (default: 0.7)
  - Lower (0.0-0.5): More factual, less varied
  - Higher (0.7-1.0): More creative, more varied
  
- `--batch-size N`: Concurrent generation tasks (default: 4)
  - Increase for faster generation on high-end GPUs
  - Decrease (1-2) if Ollama crashes or runs out of memory
  
- `--max-retries N`: Max retries per generation (default: 3)
  - Higher values = more resilient but slower
  
- `--seed SEED`: Random seed (default: 42)

#### Optional - Output Control
- `--output PATH`: Custom output JSONL path
  - Default: `subjects/datasets/{npc_key}/ollama/train.jsonl`
  
- `--no-validation`: Skip validation split
  - Generates only training set
  
- `--val-split RATIO`: Validation split ratio (default: 0.12)
  - Use 0.15 for 15% validation, 85% training

#### Optional - Health & Reliability
- `--check-health`: Verify Ollama is running and model exists before starting
- `--pull-model`: Auto-pull model from Ollama registry if missing
- `--dry-run`: Preview generation plan without generating

## Workflow Examples

### Example 1: Quick Generation with Local Model
```bash
# Generate with fastest local model (llama2)
./ucore generate-ollama subjects/history_guide.json --temperature 0.6

# Results in: subjects/datasets/history_guide/ollama/train.jsonl
# With: 12 identity + 56 teaching + 32 dialogue + 16 quest + 16 refusal = 132 total
```

### Example 2: Generation with Health Check & Auto-Pull
```bash
# Ensure Ollama is running and model is available
./ucore generate-ollama subjects/chemistry_instructor.json \
  --model llama3.1 \
  --check-health \
  --pull-model

# Ollama will pull llama3.1 if not already cached
```

### Example 3: High-Volume Generation on RTX 3060
```bash
# For 6GB VRAM systems, use smaller batches
./ucore generate-ollama subjects/fitness_coach.json \
  --model llama2 \
  --batch-size 2 \
  --temperature 0.7

# Reduced concurrency prevents OOM
```

### Example 4: Production Run with Full Validation
```bash
# Generate with custom validation split
./ucore generate-ollama subjects/astronomy_guide.json \
  --model mistral \
  --temperature 0.65 \
  --val-split 0.15 \
  --batch-size 4

# Results: 80% training (105 examples), 20% validation (27 examples)
```

### Example 5: Dry-Run Planning
```bash
# Preview without generation
./ucore generate-ollama subjects/history_guide.json --dry-run

# Output shows:
# [DRY-RUN] Would generate 132 examples:
#   identity: 12
#   teaching: 56
#   dialogue: 32
#   quest: 16
#   refusal: 16
```

## Output Structure

### Generated Files

```
subjects/datasets/{npc_key}/ollama/
├── train.jsonl              # Training examples (80-90% of total)
├── validation.jsonl         # Validation examples (10-20% of total)
├── train_manifest.json      # Generation metadata & statistics
└── generation_errors.json   # (Optional) Error log if failures occurred
```

### Manifest Example
```json
{
  "npc_key": "history_guide",
  "technique": "ollama",
  "model": "llama2",
  "generation": {
    "date": "2025-05-18T16:58:29Z",
    "seed": 42,
    "temperature": 0.7,
    "version": "ollama-v2"
  },
  "statistics": {
    "total": 132,
    "train": 116,
    "validation": 16,
    "by_category": {
      "identity": 12,
      "teaching": 56,
      "dialogue": 32,
      "quest": 16,
      "refusal": 16
    },
    "by_difficulty": {
      "beginner": 45,
      "intermediate": 48,
      "advanced": 39
    },
    "generator_stats": {
      "requests": 132,
      "successes": 132,
      "errors": 0,
      "success_rate": 1.0
    }
  }
}
```

## Performance Tuning

### For Different Hardware

#### RTX 3060 (6GB VRAM)
```bash
./ucore generate-ollama subjects/history_guide.json \
  --model llama2 \
  --batch-size 2 \
  --temperature 0.6
```
- **Expected**: ~2-3 minutes for 132 examples
- **Recommended**: Use smaller batch size to avoid OOM

#### RTX 4090 (24GB VRAM)
```bash
./ucore generate-ollama subjects/history_guide.json \
  --model llama3.1 \
  --batch-size 8 \
  --temperature 0.7
```
- **Expected**: ~30-60 seconds for 132 examples
- **Recommended**: Increase batch-size for parallelization

#### CPU Only
```bash
./ucore generate-ollama subjects/history_guide.json \
  --model qwen:4b \
  --batch-size 1 \
  --temperature 0.5
```
- **Expected**: ~10-20 minutes for 132 examples
- **Recommended**: Use smaller 4B model, batch-size=1

### Model Selection Guide

| Model | VRAM | Speed | Quality | Recommended For |
|-------|------|-------|---------|-----------------|
| llama2 | 4GB | Fast | Good | Default, RTX 3060 |
| mistral | 7GB | Medium | Good | Balanced speed/quality |
| llama3.1 | 8GB | Medium | Very Good | Quality-first |
| neural-chat | 4GB | Fast | Good | Fast generation |
| qwen:7b | 8GB | Medium | Good | Alternative |
| qwen:4b | 3GB | Fast | Fair | CPU-only, minimal VRAM |

## Troubleshooting

### Error: "Ollama is not running at http://localhost:11434"
```bash
# Start Ollama service
ollama serve

# Or if running in background, verify it's accessible
curl http://localhost:11434/api/tags
```

### Error: "Model 'llama2' not found"
```bash
# Option 1: Auto-pull during generation
./ucore generate-ollama subjects/history_guide.json --pull-model

# Option 2: Pull manually
ollama pull llama2

# Option 3: Use --check-health to verify
./ucore generate-ollama subjects/history_guide.json --check-health
```

### Generation is very slow
```bash
# Try smaller model or reduce batch size
./ucore generate-ollama subjects/history_guide.json \
  --model llama2 \
  --batch-size 1

# Or lower temperature for simpler generation
./ucore generate-ollama subjects/history_guide.json --temperature 0.5
```

### Out of memory errors
```bash
# Reduce batch size to 1-2
./ucore generate-ollama subjects/history_guide.json --batch-size 1

# Or use smaller model
./ucore generate-ollama subjects/history_guide.json --model qwen:4b
```

### Empty or low-quality generation_errors.json
```bash
# Check the main output logs
tail -50 subjects/datasets/{npc_key}/ollama/generation_errors.json

# Increase max-retries for temporary network issues
./ucore generate-ollama subjects/history_guide.json --max-retries 5
```

## Integration with Pipeline

### Full Training Workflow

```bash
# 1. Generate dataset with Ollama (new!)
./ucore generate-ollama subjects/history_guide.json --model llama3.1

# 2. Sanitize (if needed)
./ucore sanitize subjects/datasets/history_guide/ollama/train.jsonl \
  --output subjects/datasets/history_guide/ollama/train_clean.jsonl

# 3. Run dataset quality gate
./ucore dataset-eval subjects/history_guide.json --technique ollama

# 4. Train model
./ucore train subjects/history_guide.json \
  --from-spec \
  --technique ollama \
  --preset fast-3b \
  --export-gguf

# 5. Evaluate
./ucore evaluate \
  --baseline exports/history_guide/history_guide-lora-f16.gguf \
  --spec subjects/history_guide.json
```

## Implementation Details

### Architecture
- **OllamaHealthCheck**: Verifies service status and model availability
- **OllamaGeneratorV2**: Core generation engine with retry logic
- **ProgressTracker**: Real-time progress and ETA calculation
- **OllamaDatasetGenerator**: High-level orchestration

### Generation Process
1. Load subject spec and extract concepts
2. For each category (identity, teaching, dialogue, quest, refusal):
   - Generate LLM prompt with context grounding
   - Call Ollama API with retry logic
   - Parse JSON response
   - Validate with guardrails (length, character integrity)
   - Store example with metadata
3. Split into train/validation
4. Write JSONL files + manifest

### Error Handling
- **Timeout**: Automatic retry with exponential backoff
- **JSON Parse Error**: Retry with refined prompt
- **Connection Error**: Log and skip (tracked in generation_errors.json)
- **Guardrail Rejection**: Refine prompt and retry

## FAQ

**Q: Can I use a remote Ollama server?**
A: Yes! Use `--url http://<server-ip>:11434`

**Q: How do I compare Ollama vs. template generation?**
A: Compare datasets in `subjects/datasets/{npc_key}/ollama/` vs `subjects/datasets/{npc_key}/template/`

**Q: Can I generate a subset of categories?**
A: Modify the `examples_per_category` in your spec JSON, or edit after generation

**Q: Is generation resumable?**
A: Currently no, but can be added. File a feature request if needed.

**Q: How does this differ from `./ucore generate --technique ollama`?**
A: This script is optimized for local Ollama with better health checks, retry logic, and progress tracking

## Related Commands

```bash
# Compare generation techniques
./ucore generate subjects/history_guide.json --technique template  # Fast, deterministic
./ucore generate-ollama subjects/history_guide.json                # Quality, LLM-based

# Quality evaluation
./ucore dataset-eval subjects/history_guide.json --technique ollama

# Training after generation
./ucore train subjects/history_guide.json --from-spec --technique ollama
```

---

**Version**: ollama-v2  
**Author**: Unsloth_Core Team  
**Last Updated**: 2025-05-18
