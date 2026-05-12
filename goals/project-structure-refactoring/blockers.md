# Blockers: Project Structure & Workflow Refactoring

## Open Questions

- Run ID format: Proposed `{YYYYMMDD}_{preset}_{seq}` (e.g., `20260512_fast-3b_001`)? Alternative: ISO 8601 `2026-05-12T16-30-00_fast-3b`?
- Frontend approach: HTMX + Alpine.js + Chart.js (recommended — no build step) vs full React/Vue SPA?
- Should `default/` output be deleted or kept as a reference?
- Should we keep both YAML config files AND the PRESETS dict temporarily during migration, or switch immediately?
- Preferred git branching strategy? (main-only vs feature branches)

## Stop And Ask

- If any existing trained adapter fails to load after refactoring → STOP and investigate
- If any script import from `_config/paths.py` breaks → STOP before patching
- If a subject spec migration requires regenerating datasets → ASK user (generation costs time/money)
- If frontend complexity exceeds lightweight approach → STOP and discuss framework decision
- If removing PRESETS dict breaks any documented workflow → STOP and document the change

## Dangerous Or High-Risk Actions

- Deleting or moving `outputs/{npc_key}/` adapter directories — these contain trained weights
- Changing `_config/paths.py` public function signatures — imported by train.py, export.py, evaluate.py, batch_export.py, export_adapter.py
- Modifying the subject JSON schema — affects generate_dataset.py and any external tooling
- Removing the `--from-spec` CLI flag behavior — core workflow entry point

## Known Blockers

- None currently identified — the refactoring plan is well-scoped with 7 independent slices
