# Dashboard Truthfulness Audit

Date: 2026-06-05

## Scope

Dashboard/backend path:

- `src/dashboard/unity-npc-llm-training-dashboard/src/backend/routes/pipeline.ts`
- `src/dashboard/unity-npc-llm-training-dashboard/src/backend/routes/commands.ts`
- `src/dashboard/unity-npc-llm-training-dashboard/src/backend/services/command-builder.ts`
- job/process state from `src/backend/services/job-runner.ts`

## Findings

| Area | Old risk | Canonical replacement |
|---|---|---|
| NPC pipeline health | Previously derived from historical `complete`/`error` events, so stale completed runs could make a blocked NPC look healthy. | `GET /api/npc/:npc_key/status` now reads artifact registry readiness via `buildReadinessPlan()` / `buildNpcStatusFromReadinessPlan()`. |
| Stage readiness | UI/backend could infer readiness from visible cards or old run rows. | Readiness uses canonical stage prerequisites and artifact types in `.pipeline/artifacts.jsonl`. |
| Target action | Healthy state had no explicit next action. | Status reports `next_required_stage`, falling back to requested target stage when all prerequisites and target output exist. |
| Command list | Dashboard command list omitted P5/P6 CLI surfaces. | `buildAvailableCommandPayloads()` exports command metadata from `buildCommandDefinitions()`, including CLI source/command/subcommand. |
| Command schemas | `/api/command-schemas` was route-local and did not expose CLI metadata. | `buildCommandSchemaPayload()` returns typed fields/defaults/enums plus CLI metadata; tests lock P5/P6 parity. |
| Command validation | Backend start validation did not accept new target/promote/canonical-compare IDs. | `knownCommands` includes `target-plan`, `target-run`, `compare-canonical-runs`, and `promote`. |
| P5 target runner UI path | Missing from dashboard command surface. | Added `target-plan` and `target-run` with target-stage enum, dry-run default, profile, artifact-index, JSON. |
| P6 experiment/comparison UI path | Missing from dashboard command surface. | Added `compare-canonical-runs` and `promote` with registry path, dry-run/JSON defaults, required run IDs. |

## Tests Added

- `pipeline-truthfulness.test.ts`
  - status is artifact-registry-derived, not historical-complete-derived
  - evaluate is healthy only when canonical artifacts exist
- `command-schema-parity.test.ts`
  - available commands include P5/P6 surfaces
  - command schemas expose CLI metadata, typed defaults, target-stage enums, and `{npcKey}` template resolution

## Verification

```bash
npm test
npm run lint
npm run build
./ucore audit config-coherence --json
```

Observed results:

- `npm test`: 24 passed
- `npm run lint`: passed
- `npm run build`: passed
- `./ucore audit config-coherence --json`: `ok: true`
