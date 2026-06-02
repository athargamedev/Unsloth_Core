# Unsloth_Core Operator

Use when operating or changing Unsloth_Core NPC workflow: scaffold, datasets, tests, train, export, eval, feedback, manifests, and Unity LoRA readiness.

## First checks

```bash
git status --short
./ucore audit check
```

## Production Policy

- **Production data:** NotebookLM or approved grounded path only.
- **Smoke/Dev:** Template generation (`--technique template`) is for smoke tests only.
- **Active NPCs:** `history_guide`, `chef_assistant` are the only active prototypes.
- **Judge Default:** `qwen2.5:7b` for local low-VRAM (6GB) environments.

## Canonical Pipeline

```bash
# 1. Spec Validation
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready

# 2. Generation (Production: grounded path; Smoke: template)
./ucore generate data/npcs/specs/<npc>.json --technique template

# 3. Sanitize
./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
  --output data/datasets/<npc>/<technique>/train_clean.jsonl \
  --strict-canonical --require-complete-metadata

# 4. Quality Gate
./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --mode fast --judge-model qwen2.5:7b

# 5. Train & Export
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf

# 6. Evaluate (Base + LoRA)
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

## Non-negotiables

- Do not lower dataset minimums or eval thresholds to force a pass.
- Adapter GGUFs must be evaluated with their base model.
- Use `./ucore` CLI whenever possible.
- Use `quality_failures.json` as repair input.

## Canonical Paths

- Specs: `data/npcs/specs/<npc>.json`
- Reference docs: `data/npcs/reference_docs/<npc>_primer.md`
- Datasets: `data/datasets/<npc>/<technique>/`
- Clean train file: `data/datasets/<npc>/<technique>/train_clean.jsonl`
- GGUF exports: `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- Unity models: `Assets/StreamingAssets/Models/`
