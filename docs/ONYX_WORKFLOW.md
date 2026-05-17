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

## Indexing Reference Docs

Reference docs are centralized at `subjects/reference_docs/`. Each active NPC has a markdown primer there. Index them into Onyx before generation:

```bash
# Index a specific NPC's spec + primer
python scripts/onyx_index_repo.py --npc-key history_guide \
  --glob subjects/history_guide.json \
  --glob subjects/reference_docs/history_primer.md

# Or index project-wide
python scripts/onyx_index_repo.py

# Preview without indexing
python scripts/onyx_index_repo.py --dry-run
```

When creating a new NPC, `./ucore init <npc_key>` creates a stub primer at `subjects/reference_docs/{npc_key}_primer.md`. Fill it with domain content, then index.

## Generate an Onyx-Grounded Dataset

For a new subject, you can opt into targeted prep indexing before generation:

```bash
./ucore generate subjects/history_guide.json --technique onyx --onyx-prep --onyx-min-coverage 0.5 --onyx-queries 3
```

Retrieval-only, lowest resource cost:

```bash
./ucore generate subjects/history_guide.json \
  --technique onyx \
  --onyx-url http://localhost \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200
```

Output follows the normal contract:

```text
subjects/datasets/{npc_key}/onyx/train.jsonl
subjects/datasets/{npc_key}/onyx/validation.jsonl
```

Each example includes provenance metadata:

```json
{
  "source": "onyx",
  "onyx_query": "explain Rome for a beginner in history",
  "onyx_document_sets": ["history_guide"],
  "onyx_queries": ["explain Roman Empire", "define Roman Republic with examples"],
  "onyx_query_count": 2,
  "onyx_document_ids": ["doc-id"],
  "onyx_titles": ["Source Title"],
  "onyx_scores": [0.91],
  "onyx_context_chunks": 1,
  "onyx_quality_score": 0.86
}
```

## Natural Conversation Templates (v2)

Onyx generation v2 uses natural conversation templates instead of robotic "Based on our material:" framing. Templates are selected deterministically per concept×category via `_pick_variant()` using `hash(f"{concept}:{category}")`, ensuring reproducibility across regeneration runs.

**Teaching variants** (3 variants, e.g.):
- "Great question about {concept}. Here's the thing: {content} That's what really matters here."
- "Let me break down {concept} for you. The key point is: {content} Make sense?"
- "Ah, {concept} — a fascinating topic. So here's what you should know: {content}"

**Dialogue variants** (3 variants), **Identity** (2), **Quest** (2), **Refusal** (2).

Content is cleaned before insertion: all markdown headings (`#+`), bold markers (`**`), and bullet list prefixes (`-`, `*`) are stripped, and whitespace is collapsed.

## Optional Onyx + Ollama Rewrite

Use this when you want better natural language examples and have enough spare CPU/GPU:

```bash
./ucore generate subjects/history_guide.json \
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
  --spec subjects/history_guide.json \
  --preset fast-3b \
  --data subjects/datasets/history_guide/onyx/train.jsonl \
  --require-canonical \
  --strict
```

Smoke train first:

```bash
./ucore train subjects/history_guide.json --technique onyx --preset smoke
```

Then normal training:

```bash
./ucore train subjects/history_guide.json \
  --technique onyx \
  --preset fast-3b \
  --wandb \
  --export-gguf
```

## Full Pipeline

```bash
./ucore pipeline subjects/history_guide.json \
  --technique onyx \
  --preset fast-3b \
  --onyx-max-results 3 \
  --onyx-max-context-chars 1200 \
  --wandb \
  --track
```

## Why Onyx is the Default

Onyx is the default dataset generation technique. It uses local retrieval-augmented generation (RAG) from indexed source material, producing provenance-rich, grounded ChatML data without rate limits or external API dependencies. Use `--onyx-use-llm` when you want more natural examples with an Ollama rewrite pass, and fall back to `template` only for scaffolding or smoke tests.

## Debugging

- `403 Access denied`: set `ONYX_API_KEY` or log in/configure local Onyx API access.
- Empty results: index source docs in Onyx first, reduce document-set filters, or broaden subject research terms.
- Slow generation: lower `--onyx-max-results`, lower `--onyx-max-context-chars`, omit `--onyx-use-llm`.
- Weak examples: enable `--onyx-use-llm` for rewrite quality, or use v2 natural templates which are built into `generate_dataset.py` by default.
