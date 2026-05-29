# Unsloth_Core Context-Mode Patterns

Use context-mode to keep large raw outputs out of conversation memory.

## Available Tools

- `ctx_execute` — process command output in a sandbox and print only summaries.
- `ctx_execute_file` — analyze large files without loading raw bytes into context.
- `ctx_batch_execute` — gather/index multiple command outputs and search them in one round trip.
- `ctx_search(sort: "timeline")` — recover prior decisions/errors/plans after resume or compaction.

## Unsloth_Core-Specific Patterns

### Pipeline Diagnostics
```text
ctx_batch_execute([
  {label: "Quality Gate", command: "cat subjects/datasets/{npc}/template/quality_summary.json"},
  {label: "Hook Files", command: "ls outputs/{npc}/runs/*/workflow_hooks.jsonl"},
  {label: "Last Train Log", command: "ls -lt outputs/{npc}/runs/ | head -5"},
], queries: ["quality gate status", "hook trace summary", "training loss"])
```

### Large Dataset Analysis
```text
ctx_execute_file("subjects/datasets/{npc}/template/train_clean.jsonl", javascript)
```
Analyze category distribution, row counts, token lengths without loading raw data.

### Quality Gate Reports
```text
ctx_execute_file("subjects/datasets/{npc}/template/quality_summary.json", javascript)
```
Check pass rate, failing categories, distribution gaps.

### After Resume/Compaction
```text
ctx_search(sort: "timeline")
```
Always call after session resume to recover prior decisions, errors, and plan state.

## Workflow Context Module
The `_config/workflow_context.py` module centralizes resolution of techniques, models, 
and dataset paths. Use it to get a consistent view of active workflow:
```python
from _config.workflow_context import build_context
ctx = build_context("subjects/NPC_specs/{npc}.json", technique="template")
print(ctx.npc_key, ctx.dataset_train_path, ctx.model_id)
```

## Do Not
- Use context-mode tools for persistent file writes; use native Write/Edit tools.
- Store raw JSONL content, log dumps, or generated datasets in context-mode indexes.
