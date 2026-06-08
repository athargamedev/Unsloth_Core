# Migration Notes

Last verified: 2026-06-08

This file is now a historical summary plus current migration status.

## Canonical layout

- CLI shell entry: `./ucore`
- CLI Python entry for subprocess tests/tooling: `src/cli/ucore`
- Config: `etc/`
- Python config helpers: `src/config/`
- Core pipeline code: `src/core/`
- Dashboard: `src/dashboard/`
- Data: `data/`
- Artifacts: `artifacts/`
- Pipeline registry: `var/.pipeline/`

## Historical path moves

| Old path | Canonical path | Current status |
|---|---|---|
| `scripts/` | `src/core/` | legacy symlink removed |
| `_config/` | `src/config/` | legacy symlink removed |
| `configs/` | `etc/` | legacy symlink removed |
| `frontend_control/` | `src/dashboard/` | legacy symlink removed |
| `subjects/NPC_specs/` | `data/npcs/specs/` | migrated |
| `subjects/datasets/` | `data/datasets/` | migrated |
| `subjects/reference_docs/` | `data/npcs/reference_docs/` | migrated |
| `subjects/schemas/` | `data/npcs/schemas/` | legacy symlink removed |
| `outputs/` | `artifacts/models/` | legacy symlink removed |
| `exports/` | `artifacts/exports/` | legacy symlink removed |
| `eval/` | `artifacts/eval/` | legacy symlink removed |
| `logs/` | `artifacts/logs/` | legacy symlink removed |
| `.pipeline/` | `var/.pipeline/` | legacy symlink removed |

## Compatibility status

Retired:
- Root compatibility symlinks listed above
- `./ucore` as a Python-importable symlink target
- Top-level `src.core` compatibility aliases such as:
  - `src.core.dataset_eval`
  - `src.core.evaluate`
  - `src.core.generate_dataset_ollama`
  - `src.core.sanitize_dataset`
  - `src.core.smoke_test`
  - `src.core.track_eval_results`
  - `src.core.validate_subject_spec`

Current rule:
- Use canonical package imports only:
  - `src.core.dataset.*`
  - `src.core.evaluation.*`
  - `src.core.ops.*`
  - `src.core.training.*`

## Command usage

Preferred:
```bash
./ucore <command>
```

For Python subprocess tests/tooling:
```bash
python src/cli/ucore <command>
```

Do not do this:
```bash
python ./ucore <command>
```

## Notes for developers

- `src/core/__init__.py` is now a minimal package marker, not a compatibility router.
- `./ucore generate --technique ollama` is deprecated; use `./ucore generate-ollama`.
- `./ucore feedback` now routes to the working maintained pipeline orchestration, not the old dead monolith.

## Verification snapshot

Verified during the June 2026 cleanup:
- in-repo tests/imports migrated off legacy `src.core` aliases
- `src/core/__init__.py` alias shim removed
- canonical CLI/test path contract stabilized
- full non-live suite remained green after the compatibility-layer retirement
