# Local Codex MCP Servers

Configured in `.codex/config.toml`.

## GitKraken

Purpose: GitLens/GitKraken repository integration for branches, status, PRs, and issue workflows when available.

Config:

```toml
[mcp_servers.GitKraken]
command = "/home/athar/.config/Code/User/globalStorage/eamodio.gitlens/gk"
args = ["mcp", "--host=codex", "--source=gitlens", "--scheme=vscode"]
```

## ucore_context

Purpose: read-only project context for Codex. It exposes compact resources and tools for the current Unsloth_Core state without touching training artifacts.

Config:

```toml
[mcp_servers.ucore_context]
command = "python3"
args = ["/home/athar/Projects/Unsloth_Core/.codex/mcp/ucore_context_server.py"]
env = { UCORE_PROJECT_ROOT = "/home/athar/Projects/Unsloth_Core" }
```

Resources:

- `ucore://project-context`
- `ucore://commands`
- `ucore://agents`
- `ucore://project-state`
- `ucore://strategy`
- `ucore://dashboard-agents`

Tools:

- `ucore_context_summary`: returns compact source-of-truth summary and current conflict notes.
- `ucore_reference`: returns one named reference file.

Safety: read-only. It reads files under this repo only and does not run `./ucore`, tests, training, evaluation, Docker, Supabase, or Unity.

