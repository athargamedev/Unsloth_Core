# Unsloth_Core Context Maintenance

Keep agent-facing context accurate and coherent by auditing stale references and updating canonical state.

## Goal

Maintain a concise and accurate "source of truth":

1. Actual repo/tool state (highest priority).
2. `docs/project-state.md` (canonical current state).
3. `AGENTS.md` (concise entrypoint).
4. Project-local `.gemini/` memory/skills.

## Maintenance Workflow

```bash
source unsloth_env/bin/activate
# Run audit script
python src/core/ops/context_audit.py
# Check CLI help and audit
./ucore --help
./ucore audit check
```

## Stale-Reference Checklist

Flag and fix these common issues:
- Inactive NPCs (`astronomy_guide`, `fitness_coach`) presented as active.
- Template generation presented as production-ready.
- Deprecated judge models (e.g., `qwen3:latest`) used as defaults.
- Old dashboard commands or paths.
- Standalone adapter GGUF evaluation (must use base+LoRA).

## Updating Docs

1. Update `docs/project-state.md` with active NPCs, policies, and ports.
2. Update `AGENTS.md` with hard rules and quick commands.
3. Update `.gemini/skills/` with procedure changes.
4. Update Private Project Memory with stable local facts.
