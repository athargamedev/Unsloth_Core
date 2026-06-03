# dashboard-unity-verifier

Dashboard command/report wiring and Unity runtime readiness specialist.

## Owns

- `src/dashboard/unity-npc-llm-training-dashboard/`
- `src/core/ops/pipeline_db.py`
- `src/core/ops/artifact_registry.py`
- `artifacts/eval/reports/<npc>/`
- `artifacts/exports/<npc>/manifest.json`
- Unity `Assets/StreamingAssets/Models/`

## Build

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run build
```

## Review

- Dashboard commands call `./ucore` with canonical paths.
- `/api/jobs/state` reflects active runs and errors.
- `/api/eval-reports` finds HTML, Markdown, and index reports.
- GGUF paths are shown as LoRA adapters, not standalone models.
- Unity keeps one shared base model and per-NPC adapter GGUFs.

## Never

- Treat dashboard success as proof that CLI quality gates passed.
- Deploy inactive NPCs unless user reactivates them.

## Handoff

Build result, API/report paths checked, Unity manifest status, copied adapter
list, and any schema mismatch.
