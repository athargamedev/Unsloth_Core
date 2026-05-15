# Workflow Assistant Tool Path

This document describes the local Workflow Assistant tool, which is separate from the Unity NPC dataset training/export pipeline. The assistant is a frontend tool that uses local Onyx retrieval plus checked-in docs to answer workflow questions and help master the Unsloth_Core app.

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
./ucore sanitize subjects/datasets/workflow_assistant/docs/train.jsonl --strict-canonical
./ucore validate-config --spec subjects/workflow_assistant.json --preset smoke --data subjects/datasets/workflow_assistant/docs/train_clean.jsonl --require-canonical
```

These commands are for offline artifact generation and corpus auditing only. The Workflow Assistant runtime itself is powered by local Onyx retrieval and the frontend tool layer, not by Unity NPC export.

> Optional: you may prototype the docs-backed assistant corpus with `./ucore train` for offline validation, but this is not required for the runtime workflow assistant tool.

## Output paths

These paths are legacy offline artifacts for the workflow tool and corpus auditing; they are not part of the Unity NPC export pipeline.

- Raw dataset: `subjects/datasets/workflow_assistant/docs/train.jsonl`
- Validation split: `subjects/datasets/workflow_assistant/docs/validation.jsonl`
- Sanitized train set: `subjects/datasets/workflow_assistant/docs/train_clean.jsonl`
- Legacy training outputs: `outputs/workflow_assistant/runs/<run_id>/`

## Notes

- The `docs` technique is truthful here because data comes from a manifest-backed docs/report corpus, not NotebookLM or a synthetic local LLM.
- The generator lives in `scripts/generate_workflow_dataset.py` and is routed through the normal `scripts/generate_dataset.py` / `./ucore generate` path.
- The dedicated runtime tool home is `workflow_assistant/`, and its README documents the Onyx-backed local workflow assistant integration.
