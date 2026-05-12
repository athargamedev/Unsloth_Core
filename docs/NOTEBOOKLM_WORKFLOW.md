# NotebookLM Dataset Generation Workflow

This document covers the NotebookLM-based dataset generation pipeline using `scripts/generate_dataset.py`. This is the primary technique for creating high-quality, research-grounded Q&A datasets for NPC training.

## 1. Overview

The NotebookLM workflow uses Google's NotebookLM API to research topics from a subject spec, then generates synthetic Q&A pairs in ChatML format. The result is a diverse, persona-consistent dataset that covers identity, teaching, dialogue, quest, and refusal categories.

### Generation Techniques

| Technique | Source | Quality | Cost | Best For |
|-----------|--------|---------|------|----------|
| `notebooklm` | NotebookLM API (cloud) | High — research-grounded | API credits | Production datasets |
| `ollama` | Local LLM (Ollama) | Medium — creative | Free (local) | Iteration, prototyping |
| `template` | Rule-based templates | Low — repetitive | Free | Scaffolding, smoke testing |

The default technique is `notebooklm`. Each technique writes to its own subdirectory under `datasets/{npc_key}/`:

```
datasets/{npc_key}/
├── notebooklm/
│   ├── train.jsonl
│   └── validation.jsonl
├── ollama/
│   ├── train.jsonl
│   └── validation.jsonl
└── template/
    ├── train.jsonl
    └── validation.jsonl
```

## 2. Subject Spec Format

The subject spec JSON file (e.g., `subjects/chemistry_instructor.json`) defines the NPC persona, research queries, and dataset structure:

```json
{
  "npc_key": "chemistry_instructor",
  "npc_name": "ChemistryInstructor",
  "subject": "General chemistry: atoms, molecules, elements...",
  "system_prompt": "You are ChemistryInstructor... Rules: 1-3 sentences...",
  "research": [
    {
      "query": "General chemistry basics atoms molecules periodic table...",
      "mode": "fast",
      "from": "web",
      "source_policy": "text-web"
    }
  ],
  "dataset": {
    "examples_per_category": {
      "identity": 8,
      "teaching": 32,
      "dialogue": 16,
      "quest": 8,
      "refusal": 8
    }
  }
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `npc_key` | Unique snake_case identifier (used for filenames) |
| `npc_name` | PascalCase display name used in persona |
| `subject` | High-level subject description |
| `system_prompt` | Full NPC system prompt with behavioral rules |
| `research` | Array of NotebookLM research queries with mode and source policy |
| `dataset.examples_per_category` | Number of examples to generate per category (total = sum) |

### Dataset Categories

| Category | Description | Example Count (above) |
|----------|-------------|-----------------------|
| `identity` | Persona introduction and self-identification | 8 |
| `teaching` | Core subject knowledge explanations | 32 |
| `dialogue` | Multi-turn conversational interactions | 16 |
| `quest` | Challenge or puzzle interactions | 8 |
| `refusal` | Graceful out-of-scope refusal | 8 |

The total examples (72 in this case) are split 88% train / 12% validation, stratified by category.

## 3. Usage

### Basic Dataset Generation

Generate a dataset from a subject spec using the default (NotebookLM) technique:

```bash
python scripts/generate_dataset.py subjects/chemistry_instructor.json
```

Output:
- Train: `datasets/chemistry_instructor/notebooklm/train.jsonl`
- Validation: `datasets/chemistry_instructor/notebooklm/validation.jsonl`

### With Specific Technique

```bash
# NotebookLM (cloud, research-grounded)
python scripts/generate_dataset.py subjects/chemistry_instructor.json --technique notebooklm

# Ollama (local LLM)
python scripts/generate_dataset.py subjects/chemistry_instructor.json --technique ollama

# Template (rule-based, no LLM required)
python scripts/generate_dataset.py subjects/chemistry_instructor.json --technique template
```

### Custom Output Path

Override the default output location:

```bash
python scripts/generate_dataset.py subjects/chemistry_instructor.json \
    --output my/custom/path.jsonl
```

### Ollama-Specific Flags

When using `--technique ollama`, you can also pass Ollama-specific flags:

```bash
python scripts/generate_dataset.py subjects/chemistry_instructor.json \
    --technique ollama \
    --model llama3.1:latest \
    --multi-turn-ratio 0.4 \
    --temperature 0.8
```

### Validation Split Control

```bash
# Skip validation split entirely
python scripts/generate_dataset.py subjects/chemistry_instructor.json \
    --no-validation

# Custom validation split ratio
python scripts/generate_dataset.py subjects/chemistry_instructor.json \
    --val-split 0.15
```

## 4. Data Format (ChatML)

Generated datasets use the ChatML message format with `role` and `content` fields:

```json
{
  "messages": [
    {"role": "system", "content": "You are ChemistryInstructor..."},
    {"role": "user", "content": "What is an atom?"},
    {"role": "assistant", "content": "An atom is the basic building block of matter..."}
  ],
  "metadata": {
    "npc_key": "chemistry_instructor",
    "category": "teaching",
    "source": "notebooklm:chemistry_instructor"
  }
}
```

Each line in the JSONL file is a single training example. The `metadata` field tracks provenance (source technique, category, concept) for analysis and filtering.

### Multi-Turn Examples

When using LLM generation (`ollama` or `notebooklm`), some examples include multi-turn dialogues (2-3 rounds):

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "What is a mole?"},
    {"role": "assistant", "content": "A mole is a unit for counting particles..."},
    {"role": "user", "content": "How do I calculate moles?"},
    {"role": "assistant", "content": "Divide the mass by the molar mass..."}
  ],
  "metadata": {"category": "multi_turn", ...}
}
```

## 5. Dataset Structure

```
datasets/{npc_key}/
├── {technique}/
│   ├── train.jsonl              # 88% of examples
│   └── validation.jsonl         # 12% of examples
└── {technique}/                 # Another technique's output
    ├── train.jsonl
    └── validation.jsonl
```

### Split Strategy

The 88/12 train/validation split is performed **stratified by category** to ensure each category is represented proportionally in both splits. The minimum validation count per category is 1.

## 6. Technique Comparison

| Aspect | NotebookLM | Ollama | Template |
|--------|-----------|--------|----------|
| **Data source** | Web research via API | Local LLM inference | Hardcoded templates |
| **Quality** | High — factual, diverse | Medium — creative, varied | Low — repetitive |
| **Cost** | NotebookLM API credits | Free (local GPU/CPU) | Free |
| **Speed** | Slow (API calls) | Medium (local inference) | Instant |
| **Multi-turn** | Yes | Yes (`--multi-turn-ratio`) | No |
| **Research-grounded** | Yes | No | No |
| **Best for** | Production datasets | Iteration, prototyping | Smoke testing |

## 7. Troubleshooting

### No Research Queries Defined

```
[warn] No research queries defined for this NPC.
```

Add a `research` array to the subject spec with at least one query:

```json
"research": [{"query": "your topic", "mode": "fast", "from": "web"}]
```

### Generation Fails with API Error

- Verify the active technique has all required dependencies
- For `notebooklm`: ensure API credentials are configured
- For `ollama`: ensure Ollama is running (`ollama serve`) and the model is pulled
- For `template`: no dependencies needed; should always work

### JSONL Format Issues

If training fails with parsing errors:

- Verify each line in the JSONL is valid JSON
- Check that messages have `role` and `content` string fields (never arrays or objects)
- The sanitization step runs automatically during generation, but if editing by hand, ensure `content` values are strings

### Missing Validation Set

The validation set is only generated when `total_examples > 5`. For very small datasets, increase `examples_per_category` values or use `--val-split` to adjust the ratio.
