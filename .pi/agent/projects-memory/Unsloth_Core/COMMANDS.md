# Unsloth_Core Commands

Always activate the Python environment before Python pipeline work:

```bash
source unsloth_env/bin/activate
```

## Health / Audit

```bash
./ucore audit check
python scripts/ops/preflight.py --phase train --preset fast-3b --json
```

## Dataset Flow

```bash
./ucore validate-spec subjects/NPC_specs/history_guide.json --generation-ready
./ucore generate subjects/NPC_specs/history_guide.json --technique template
./ucore sanitize subjects/datasets/history_guide/template/train.jsonl \
  --output subjects/datasets/history_guide/template/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval subjects/NPC_specs/history_guide.json \
  --technique template --mode fast --judge-model qwen3:latest
```

## Train / Export / Eval

```bash
./ucore train subjects/NPC_specs/history_guide.json --technique template --preset fast-3b --export-gguf
./ucore export history_guide
./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf \
  --spec subjects/NPC_specs/history_guide.json --report-html
```

## Dashboard / Backend

```bash
npm run dev:modular
npm run build
npm run start:modular
python scripts/ops/setup_admin_key.py
```

## Supabase

```bash
supabase status
supabase start
./ucore supabase-check --npc-key history_guide
```

## Context / Memory

```text
Use memory_search for durable project/user/failure context.
Use ctx_search(sort: "timeline") after resume/compact.
Use ctx_execute/ctx_execute_file for large-output analysis.
```
