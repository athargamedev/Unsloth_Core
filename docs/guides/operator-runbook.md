# Unsloth_Core Operator Runbook

This is the short human-readable companion to the Hermes skill:
`software-development/unsloth-core-project-playbook`.

Use it when you are about to touch dataset generation, training, export, evaluation, or dashboard wiring in this repo.

## Canonical facts

- **Active NPCs (3 total):** `history_guide`, `chef_assistant`, and `marvel_heroes_instructor`. Previously active NPCs
  (`astronomy_guide`, `fitness_coach`) have been removed — their specs and datasets no
  longer exist in the repository.
- NPC specs live at `data/npcs/specs/{npc_key}.json`
- Primers live at `data/npcs/reference_docs/{npc_key}_primer.md`
- Canonical training runs live at `artifacts/models/{npc_key}/runs/{run_id}/`
- `artifacts/models/{npc_key}/best` and `artifacts/models/{npc_key}/latest` are pointers, not duplicate run folders
- GGUF exports live at `artifacts/exports/{npc_key}/`
- Eval reports live at `artifacts/eval/reports/{npc_key}/`
- Compare reports live at `artifacts/eval/comparisons/`
- Use `./ucore` first whenever a repo command exists

## Standard pipeline

1. Validate the subject spec
   ```bash
   ./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
   ```

2. Generate the dataset
   ```bash
   # Production (Ollama):
   ./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
   # Or direct llama.cpp:
   ./ucore generate-local --model <gguf> data/npcs/specs/<npc>.json --fresh
   # Smoke/dev only:
   # ./ucore generate data/npcs/specs/<npc>.json --technique template
   ```

3. Sanitize the dataset
   ```bash
   ./ucore sanitize data/datasets/<npc>/<technique>/train.jsonl \
     --output data/datasets/<npc>/<technique>/train_clean.jsonl \
     --strict-canonical --require-complete-metadata
   ```

4. Run dataset quality gating
   ```bash
   ./ucore dataset-eval data/npcs/specs/<npc>.json --technique <technique> --judge-model qwen2.5:7b
   ```

5. Train
   ```bash
   ./ucore train data/npcs/specs/<npc>.json --technique <technique> --preset fast-3b --export-gguf
   ```

6. Evaluate
   ```bash
   ./ucore evaluate \
     --baseline artifacts/exports/<npc>/<npc>-lora-f16.gguf \
     --candidate artifacts/models/<npc>/runs/<run_id> \
     --base-model /path/to/llama-3.2-3b-instruct-q4_k_m.gguf \
     --spec data/npcs/specs/<npc>.json \
     --report-html --judge --judge-model qwen2.5:7b
   ```

## Output layout

- New training artifacts should land in `artifacts/models/<npc_key>/runs/<run_id>/`
- `best` should point to the best run
- `latest` should point to the newest run
- If `best` or `latest` are stale files or folders, replace them safely with a new pointer
- If `best` is missing, use `latest`; if both are missing, fall back to the newest valid run in `runs/`

## Debugging order

When a workflow looks wrong:

1. Check `src/core/ops/env_loader.py` first
2. Then check `src/core/training/train.py`
3. Then check `src/core/export/export.py`
4. Then check `src/core/evaluation/evaluate.py`
5. Then check `src/dashboard/unity-npc-llm-training-dashboard/server.ts`
6. Then verify the filesystem, API, and browser in that order

## Common mistakes

- Hardcoding `outputs/<npc>/best` when the code should resolve `latest` or the newest valid run
- Confusing the canonical run folder with the pointer symlinks
- Training on `train.jsonl` when `train_clean.jsonl` already exists
- Assuming the reports list is empty when the UI may just be stale
- Letting dataset quality failures get hidden instead of used to regenerate better data
- Wiring the dashboard to only baseline/candidate/spec and forgetting the rest of the evaluation flags

## Useful verification commands

```bash
python -m py_compile src/core/training/train.py src/core/export/export.py src/core/evaluation/evaluate.py
pytest -q tests/test_pipeline_boundaries.py
npm run build --prefix src/dashboard/unity-npc-llm-training-dashboard
```

## Quick inspection snippet

```bash
python - <<'PY'
from src.core.ops.env_loader import load_env
npc = "<npc>"
print("output:", paths.output_dir(npc))
print("export:", paths.export_dir(npc))
print("best:", paths.best_run_dir(npc))
print("latest:", paths.latest_run_dir(npc))
PY
```

## Rule of thumb

If you are unsure which artifact should be used:

- prefer canonical over legacy paths
- prefer explicit helper functions over ad hoc string joins
- prefer symlink pointers over duplicate folders
- prefer backend-owned state over frontend inference
- verify with tests/build/browser instead of guessing
