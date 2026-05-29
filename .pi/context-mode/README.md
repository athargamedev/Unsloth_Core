# Project Context-Mode Notes

Use context-mode to keep large raw outputs out of conversation memory.

- `ctx_execute` — process command output in a sandbox and print only summaries.
- `ctx_execute_file` — analyze large files without loading raw bytes into context.
- `ctx_batch_execute` — gather/index multiple command outputs and search them in one round trip.
- `ctx_search(sort: "timeline")` — recover prior decisions/errors/plans after resume or compaction.

Do not use context-mode tools for persistent file writes; use Pi `write` or `edit`.
