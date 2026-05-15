# Workflow Assistant Tool

This folder contains the dedicated Workflow Assistant tool for Unsloth_Core.

## Purpose

The Workflow Assistant is a developer-facing tool for mastering the Unsloth_Core app. It is not a Unity NPC dataset, and it is not intended for deployment as a Unity gameplay NPC.

Instead, this tool:

- uses local Onyx retrieval to ground answers in indexed repo documentation and workflow sources
- keeps improving as the Onyx index is refreshed with repo docs, subjects, and reports
- powers the frontend workflow assistant experience separately from NPC training
- is a runtime tool for the dashboard, not a Unity NPC deployment artifact

## Local Onyx Integration

To use the Workflow Assistant with Onyx:

1. Index the repo using the existing helper:
   ```bash
   python scripts/onyx_index_repo.py
   ```
2. Set local Onyx environment variables in the repo `.env` or your shell:
   ```bash
   export ONYX_BASE_URL=http://localhost
   export ONYX_SEARCH_MODE=admin
   export ONYX_API_KEY=...
   ```
3. The dashboard assistant now includes Onyx search context when answering workflow questions.

## Notes

- This tool lives separately from `datasets/workflow_assistant/docs/`.
- The legacy docs-backed dataset path remains available for offline corpus generation, validation, and historical artifact tracking.
- The runtime assistant behavior is now designed as a local tool, not a Unity NPC training asset.
