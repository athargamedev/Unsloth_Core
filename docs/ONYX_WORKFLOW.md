# Onyx Retrieval Workflow

This document explains how the local Onyx server improves Unsloth_Core dataset generation and training without overloading the workstation.

## Purpose

Onyx is used as a local retrieval layer, not as a training backend. It should hold indexed source material such as project docs, subject notes, Unity dialogue references, PDFs, previous datasets, and eval reports. `Unsloth_Core` can then retrieve small, relevant chunks and use them to generate source-grounded ChatML datasets.

## Resource Policy

Defaults are conservative for a local desktop:

- Retrieval-only by default: no extra local LLM generation unless `--onyx-use-llm` is passed.
- Small top-k: `--onyx-max-results 4` by default.
- Bounded context: `--onyx-max-context-chars 1800` per example by default.
- Search caching inside one generation run: repeated category/concept queries do not hit Onyx again.
- No automatic indexing during training: index documents in Onyx separately so training jobs do not compete with ingestion/embedding jobs.

Use `--onyx-use-llm` only when the local Ollama model can run comfortably while Onyx is already indexed. For weaker hardware, prefer retrieval-only Onyx generation, then train with `--preset smoke` or `--preset safe-any` first.

## Local Server Requirements

The integration calls:

```text
GET  {ONYX_BASE_URL}/api/health
POST {ONYX_BASE_URL}/api/admin/search   # default, resource-conscious, avoids LLM context selection
POST {ONYX_BASE_URL}/api/search         # optional ONYX_SEARCH_MODE=search, can trigger Onyx LLM filtering
```

Defaults:

```bash
export ONYX_BASE_URL=http://localhost
export ONYX_SEARCH_MODE=admin
# Set only if local Onyx auth requires it:
export ONYX_API_KEY=...
```

`./ucore` also reads these from the repo-root `.env` file, which is gitignored. On this machine, `/api/search` authenticated successfully but timed out during Onyx LLM context selection, so the default is `admin` search to keep dataset generation lightweight and avoid competing with training resources.

## Generate an Onyx-Grounded Dataset

First connect/update this repo in Onyx using the ingestion helper:

```bash
python scripts/onyx_index_repo.py
```

That helper indexes docs, subject specs, configs, and key workflow scripts only; it skips generated datasets, outputs, exports, venvs, frontend runtime blobs, and model artifacts. Use `--dry-run` to preview, or `--glob 'docs/**/*.md' --limit 10` for a smaller test.

Retrieval-only, lowest resource cost:

```bash
./ucore generate subjects/chemistry_instructor.json \
  --technique onyx \
  --onyx-url http://localhost \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200
```

Output follows the normal contract:

```text
datasets/{npc_key}/onyx/train.jsonl
datasets/{npc_key}/onyx/validation.jsonl
```

Each example includes provenance metadata:

```json
{
  "source": "onyx",
  "onyx_query": "explain atoms for a beginner in chemistry",
  "onyx_document_ids": ["doc-id"],
  "onyx_titles": ["Source Title"],
  "onyx_scores": [0.91],
  "onyx_context_chunks": 1
}
```

## Optional Onyx + Ollama Rewrite

Use this when you want better natural language examples and have enough spare CPU/GPU:

```bash
./ucore generate subjects/chemistry_instructor.json \
  --technique onyx \
  --onyx-use-llm \
  --model llama3.1:latest \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200
```

This still uses Onyx as factual grounding and asks Ollama only to rewrite compact examples from retrieved chunks.

## Train From Onyx Data

Preflight:

```bash
./ucore validate-config \
  --spec subjects/chemistry_instructor.json \
  --preset fast-3b \
  --data datasets/chemistry_instructor/onyx/train.jsonl \
  --require-canonical \
  --strict
```

Smoke train first:

```bash
./ucore train subjects/chemistry_instructor.json --technique onyx --preset smoke
```

Then normal training:

```bash
./ucore train subjects/chemistry_instructor.json \
  --technique onyx \
  --preset fast-3b \
  --wandb \
  --export-gguf
```

## Full Pipeline

```bash
./ucore pipeline subjects/chemistry_instructor.json \
  --technique onyx \
  --preset fast-3b \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200 \
  --wandb \
  --track
```

## Why Onyx is the Default

Onyx is now the default dataset generation technique. It uses local retrieval-augmented generation (RAG) from indexed source material, producing provenance-rich, grounded ChatML data without rate limits or external API dependencies. Use `onyx --onyx-use-llm` when you want more natural examples with an Ollama rewrite pass, and fall back to `template` only for scaffolding or smoke tests.

## Debugging

- `403 Access denied`: set `ONYX_API_KEY` or log in/configure local Onyx API access.
- Empty results: index source docs in Onyx first, reduce document-set filters, or broaden `subjects/*.json` research terms.
- Slow generation: lower `--onyx-max-results`, lower `--onyx-max-context-chars`, omit `--onyx-use-llm`.
- Weak examples: index better source docs or enable `--onyx-use-llm` for rewrite quality.
