# Contributing to Unsloth_Core

## Setup

See [SETUP.md](SETUP.md) for full dev environment setup — clone through Unsloth installation, Ollama, Supabase, and dashboard.

## Code Style

- **Python:** PEP 8. Use `black` for formatting, `ruff` for linting.
- **TypeScript/React:** Standard Prettier config in the dashboard package.
- **Shell:** Prefer `.py` scripts over shell scripts for logic-heavy operations.
- **Markdown:** One sentence per line (hard wrap at ~100 chars) for diff readability.

## PR Process

1. **Branch naming:** `<type>/<short-description>` — e.g. `fix/train-vram-leak`, `feat/ollama-batch-gen`
2. **Commit messages:** Conventional commits — `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
3. **PR body:** Describe what changed, why, and how to test. Include `Closes #N` if applicable.
4. **Review expectations:**
   - All tests must pass
   - No new lint warnings
   - Pipeline scripts must not break existing commands
   - If adding a new `./ucore` subcommand, update `docs/reference/cli-commands.md`
5. **Merge:** Squash merge into `main`. Branch deleted after merge.

## How to Add a New NPC

1. Create spec: `data/npcs/specs/<npc>.json` (see existing specs for schema)
2. Create reference doc: `data/npcs/reference_docs/<npc>_primer.md`
3. Validate spec: `./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready`
4. Generate dataset: `./ucore generate data/npcs/specs/<npc>.json --technique <technique>`
5. Sanitize: `./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl --output train_clean.jsonl --strict-canonical`
6. Run dataset quality gate: `./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --mode fast`
7. Train: `./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf`
8. Update `docs/project-state.md` with new NPC status

See `docs/training-workflow.md` for detailed pipeline docs.

## How to Run Tests

```bash
# All tests
pytest tests/

# Specific area
pytest tests/test_pipeline_dag_registry.py -v

# Compile-check all scripts
python -m py_compile scripts/**/*.py

# Full audit
./ucore audit check
```

## Agent Context Contribution Guidelines

When updating context files (skills, agent briefs, docs):

1. **One fact, one file.** If a fact is already in `AGENTS.md` or `docs/project-state.md`, reference it — don't copy.
2. **Always update `last_verified`** in YAML frontmatter when you touch a file.
3. **Skills reference, don't duplicate.** Skills may include example commands but canonical paths/rules live in Tier 0-2 files.
4. **Standard agent-brief template** — all agent briefs should match `docs/reference/agent-brief-template.md`.
5. **Run stale-reference audit** after context changes:

```bash
python src/core/ops/context_audit.py
```

## Questions?

Open an issue, or ask in the project's chat channel.
