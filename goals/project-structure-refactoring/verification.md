# Verification: Project Structure & Workflow Refactoring

## Commands

| # | Command | Purpose | Expected pass condition | Evidence location |
| --- | --- | --- | --- | --- |
| 1 | `python scripts/train.py subjects/chemistry_instructor.json --from-spec --preset fast-3b --dry-run` | Verify preset loading from YAML | Prints config with preset values applied, no errors | `progress.jsonl` |
| 2 | `python scripts/train.py --show-presets` | Verify preset discovery | Lists all presets with descriptions | `progress.jsonl` |
| 3 | `ls outputs/chemistry_instructor/runs/` | Verify run ID output structure | Directory exists with run ID subdirectory (e.g., `20260512_fast-3b_001/`) | `progress.jsonl` |
| 4 | `cat outputs/chemistry_instructor/runs/*/config.yaml` | Verify frozen config copy | Valid YAML matching the training config | `progress.jsonl` |
| 5 | `cat outputs/chemistry_instructor/runs/*/metrics.json` | Verify metrics extraction | Valid JSON with loss, eval_loss, learning_rate | `progress.jsonl` |
| 6 | `ls -la outputs/chemistry_instructor/latest` | Verify latest symlink | Symlink exists pointing to a run directory | `progress.jsonl` |
| 7 | `python scripts/compare_runs.py chemistry_instructor --runs RUN1,RUN2 2>&1 > /dev/null && echo "Tool exists"` | Verify comparison tool exists | Script runs without import errors | `progress.jsonl` |
| 8 | `python3 -c "import json; d=json.load(open('subjects/chemistry_instructor.json')); print(d.keys())"` | Verify subject schema | Keys include: identity, teaching, dialogue, quest, refusal, research_queries | `progress.jsonl` |
| 9 | `python3 -c \"from _config import paths; print(paths.export_gguf_path('test', 'unsloth/Llama-3.2-3B-Instruct-bnb-4bit', 'q4_k_m'))\"` | Verify paths API unchanged | Prints expected path without errors | `progress.jsonl` |
| 10 | `ls docs/NOTEBOOKLM_WORKFLOW.md docs/TEMPLATE_WORKFLOW.md docs/TRAINING_WORKFLOW.md docs/EVALUATION_WORKFLOW.md 2>&1` | Verify workflow docs exist | All 4 new docs exist alongside OLLAMA_WORKFLOW.md | `progress.jsonl` |
| 11 | `ls frontend/app.py 2>&1` | Verify frontend exists | Frontend app.py exists | `progress.jsonl` |
| 12 | `ls outputs/default/ 2>&1 \|\| echo "Directory removed"` | Verify cleanup | `default/` directory removed or moved | `progress.jsonl` |
| 13 | `git status` | Verify git setup | Clean git status with proper .gitignore | `progress.jsonl` |
| 14 | `python scripts/export.py bible_instructor --skip-f16 2>&1 \| head -5` | Verify legacy export works | Exports without errors | `progress.jsonl` |

## Manual Checks

- [ ] Open each workflow doc and verify: architecture pipeline, usage commands, flag reference, comparison table (old vs new), troubleshooting steps
- [ ] Run `python scripts/train.py subjects/marvel_instructor.json --from-spec --preset quality-1.7b --dry-run` — verify preset values correct for quality-1.7b
- [ ] Launch frontend (`python frontend/app.py`), verify: config browser, run explorer with loss chart, GPU/memory panel, export manager
- [ ] Check that `configs/presets/` contains all presets previously in train.py PRESETS dict (smoke, fast-0.5b, fast-1.7b, fast-3b, quality-1.7b, safe-any)
- [ ] Verify `configs/models/` contains model configs from `configs/base_configs/`
- [ ] Check AGENTS.md is updated to reflect new project structure

## Evidence Rules

- Record verification results in `progress.jsonl`.
- Include command, status (PASS/FAIL), timestamp, and artifact path when available.
- If any command fails, document the error and whether it's a blocker, then ask the user.
- Do not mark the goal complete until all critical commands (1, 3, 10, 11, 13) pass.
