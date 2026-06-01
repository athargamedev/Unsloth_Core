# Folder Reorganization Migration (2026-06-01)

## What Changed

The project structure has been reorganized for clarity, modularity, and maintainability. Phases 1 through 5 have been fully completed as of 2026-06-01.

### Mapping Table

| Old Path | New Canonical Path | Phase | Status (As of 2026-06-01) |
|----------|--------------------|-------|---------------------------|
| `scripts/` | `src/core/` | Phase 1 | Completed |
| `_config/` | `src/config/` | Phase 1 | Completed |
| `ucore` | `src/cli/ucore` | Phase 2 | Completed |
| `frontend_control/` | `src/dashboard/` | Phase 2 | Completed |
| `configs/` or `_config/` (yaml templates) | `etc/` | Phase 3 | Completed |
| `subjects/NPC_specs/` | `data/npcs/specs/` | Phase 4 | Completed |
| `subjects/datasets/` | `data/datasets/` | Phase 4 | Completed |
| `subjects/reference_docs/` | `data/npcs/reference_docs/` | Phase 4 | Completed |
| `subjects/schemas/` | `data/npcs/schemas/` | Phase 4 | Completed |
| `outputs/` | `artifacts/models/` | Phase 5 | Completed |
| `exports/` | `artifacts/exports/` | Phase 5 | Completed |
| `eval/` | `artifacts/eval/` | Phase 5 | Completed |
| `logs/` | `artifacts/logs/` | Phase 5 | Completed |

---

## Backward Compatibility

To maintain flawless operation of existing tools, legacy scripts, and third-party integrations, we have implemented backward-compatibility at two levels:

1. **Root Symlinks**: Root-level symlinks have been set up so that older path schemas still resolve perfectly on disk.
   - `./ucore` → `src/cli/ucore`
   - `_config/` → `src/config/`
   - `scripts/` → `src/core/`
   - `frontend_control/` → `src/dashboard/`
   - `subjects/` → `data/` (with internal maps/symlinks)
   - `outputs/` → `artifacts/models/`
   - `exports/` → `artifacts/exports/`
   - `eval/` → `artifacts/eval/`
   - `logs/` → `artifacts/logs/`

2. **Python Path Helper Fallbacks**: We implemented robust Python fallback helpers in `src/config/paths.py`. If a script attempts to look up or construct paths using old constants, the helpers automatically detect and map them to their new canonical locations, preventing breaking changes at runtime.

---

## New Directory Structure

The canonical project workspace is structured as follows:

```
Unsloth_Core/
├── artifacts/             # Outputs, exports, logs, evaluation reports
│   ├── eval/              # Evaluation output files and summaries
│   ├── exports/           # Exported GGUF adapters and merges
│   ├── logs/              # Training and preflight logs
│   └── models/            # Fine-tuned model adapters and runs
├── data/                  # NPC specification files, datasets, primers, schemas
│   ├── datasets/          # Processed, clean datasets per NPC
│   └── npcs/
│       ├── reference_docs/ # Primer files and reference documents
│       ├── schemas/       # NPC spec validation schemas
│       └── specs/         # Subject specifications in JSON format
├── etc/                   # Shared templates and CLI configurations
├── src/                   # Source code
│   ├── cli/               # CLI tools, including the canonical `./ucore` entrypoint
│   ├── config/            # Configuration management, including `paths.py`
│   ├── core/              # Training, dataset generation, sanitation, and evaluation logic
│   └── dashboard/         # Visual web dashboard and frontend code
```

---

## For Developers

### Running Commands
All commands can be run canonical or legacy:
```bash
# Still works (via symlink)
./ucore generate history_guide

# Also works (canonical path)
./src/cli/ucore generate history_guide
```

### Python Imports
New code should transition to preferred import patterns:
```python
# NEW (preferred)
from src.core.dataset import generate_dataset
from src.config.paths import DATASET_ROOT

# OLD (still works via symlinks and path mapping, but deprecated)
from scripts.dataset import generate_dataset
from _config.paths import DATASET_ROOT
```

---

## Next Steps

We are entering the cleanup and documentation phases (Phases 6-8). Please report any broken paths, import errors, or script issues to the maintenance team.

## Questions?
See `AGENTS.md` and `docs/project-state.md` for updated paths and pipeline descriptions.
