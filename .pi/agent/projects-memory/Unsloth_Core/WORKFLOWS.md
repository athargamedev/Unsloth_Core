# Reusable Workflows

## Before Complex Pipeline Operations

1. Read `AGENTS.md` relevant section.
2. Search memory for prior failures/decisions:
   - project conventions: `memory_search(..., project="Unsloth_Core")`
   - failures/tool quirks: `memory_search(..., target="failure")`
3. Run a lightweight audit/preflight where appropriate:
   - `./ucore audit check`
   - `python scripts/ops/preflight.py --phase train --preset <preset> --json`
4. Check generated artifacts, hook files, and quality gate summaries before spending GPU time.

## New NPC Dataset

1. Read spec and primer first.
2. Validate generation readiness.
3. Generate using selected technique.
4. Sanitize to `train_clean.jsonl` with strict canonical metadata.
5. Run dataset-eval fast gate.
6. Fix generator/prompts/primer/rows if gate fails; do not weaken thresholds first.

## Dashboard Work

1. Prefer modular backend paths under `src/backend/` and `server-modular.ts`.
2. Dashboard must reflect canonical backend state and process artifacts.
3. Use React Query for server state and Zustand for UI state.
4. Preserve user-facing empty/loading/error states.

## Memory Hygiene

1. Use `compact-memory-extraction` when extracting durable facts.
2. Search before adding.
3. Consolidate near-duplicates.
4. Store procedures as skills, not long memory entries.
5. Never store raw logs, secrets, generated datasets, or temporary TODOs.
