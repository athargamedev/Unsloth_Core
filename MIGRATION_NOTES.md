# Folder Reorganization Migration (2026-06-01)

## What Changed

The project structure has been reorganized for clarity and maintainability:

| Old Path | New Canonical Path |
|----------|-------------------|
| `scripts/` | `src/core/` |
| `_config/` | `src/config/` |
| `ucore` | `src/cli/ucore` |
| `frontend_control/` | `src/dashboard/` |
| `outputs/` | `artifacts/models/` (Phase 5) |
| `exports/` | `artifacts/exports/` (Phase 5) |
| `eval/` | `artifacts/eval/` (Phase 5) |
| `logs/` | `artifacts/logs/` (Phase 5) |

## Backward Compatibility

Symlinks at the root level ensure old paths still work:
- `./ucore` → `src/cli/ucore`
- `_config/` → `src/config/`
- `scripts/` → `src/core/`
- `frontend_control/` → `src/dashboard/`

## For Developers

### Running Commands
```bash
# Still works (via symlink)
./ucore generate history_guide

# Also works (canonical path)
./src/cli/ucore generate history_guide
```

### Python Imports
New code should use:
```python
# NEW (preferred)
from src.core.dataset import generate_dataset
from src.config.paths import DATASET_ROOT

# OLD (still works via symlinks, but deprecated)
from scripts.dataset import generate_dataset
from _config.paths import DATASET_ROOT
```

### Next Steps (Future Phases)
- **Phase 3**: Configuration files → `etc/`
- **Phase 4**: NPC data → `data/npcs/`
- **Phase 5**: Artifacts → `artifacts/`, state → `var/`
- **Phase 6-8**: Cleanup & documentation

## Questions?
See `AGENTS.md` and `docs/PROJECT_STATE.md` for updated paths.
