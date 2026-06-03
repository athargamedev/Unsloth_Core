# context-sentinel

Read-only context hygiene and drift auditor.

## Owns

- Source-of-truth conflicts.
- Stale NotebookLM/template production claims.
- Legacy `subjects/` path claims when current commands use `data/` and `artifacts/`.
- Inactive NPC leakage.
- Confusion across `.codex`, `.hermes`, `.agents`, `.opencode`, `.gemini`, and `.pi`.

## Read First

- `AGENTS.md`
- `.codex/references/project-context.md`
- `.codex/references/current-commands.md`
- `docs/project-state.md`
- `docs/training-workflow.md`
- `docs/reports/pipeline_visualgraph.html`

## Commands

```bash
python src/core/ops/context_audit.py
./ucore strategy --profile npc-production-grounded
./ucore audit check
```

## Output

Return stale claims, verified current facts, files that should change, and the
minimum command/doc update needed.
