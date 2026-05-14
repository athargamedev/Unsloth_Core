# Workflow Assistant Dataset + Training Path

This workflow is the canonical path for `subjects/workflow_assistant.json`.

## Goal

Train a repo-helpful frontend assistant from safe checked-in docs and structured reports only.

## Safe corpus

- Manifest: `docs/corpora/workflow_assistant_docs.json`
- Allowed sources: checked-in markdown docs and structured validation reports
- Excluded sources: runtime logs, `outputs/`, `exports/`, `.runtime/registry.json`, secrets, machine-local state

## Commands

```bash
./ucore validate-spec subjects/workflow_assistant.json
./ucore generate subjects/workflow_assistant.json --technique docs
./ucore sanitize datasets/workflow_assistant/docs/train.jsonl --strict-canonical
./ucore validate-config --spec subjects/workflow_assistant.json --preset smoke --data datasets/workflow_assistant/docs/train_clean.jsonl --require-canonical
```

If you want to train after validation:

```bash
./ucore train subjects/workflow_assistant.json --preset smoke --technique docs
```

## Output paths

- Raw dataset: `datasets/workflow_assistant/docs/train.jsonl`
- Validation split: `datasets/workflow_assistant/docs/validation.jsonl`
- Sanitized train set: `datasets/workflow_assistant/docs/train_clean.jsonl`
- Training outputs: `outputs/workflow_assistant/runs/<run_id>/`

## Notes

- The `docs` technique is truthful here because data comes from a manifest-backed docs/report corpus, not NotebookLM or a synthetic local LLM.
- The generator lives in `scripts/generate_workflow_dataset.py` and is routed through the normal `scripts/generate_dataset.py` / `./ucore generate` path.
