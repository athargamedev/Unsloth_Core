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
# After resume/compact — recover prior session context
ctx_search(sort: "timeline")

# Pipeline diagnostics — quality gate + hooks + logs in one call
ctx_batch_execute([
  {label: "Quality Gate", command: "cat subjects/datasets/{npc}/template/quality_summary.json"},
  {label: "Hook Files", command: "cat outputs/{npc}/runs/*/workflow_hooks.jsonl"},
], queries: [...])

# Large file analysis (datasets, training logs, eval reports)
ctx_execute_file("subjects/datasets/{npc}/template/train_clean.jsonl", javascript)
ctx_execute_file("outputs/{npc}/runs/*/training_log.txt", javascript)

# Workflow Context inspection
python -c "from _config.workflow_context import build_context; ctx = build_context('subjects/NPC_specs/{npc}.json', technique='template'); print(ctx)"
```
