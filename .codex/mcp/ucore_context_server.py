#!/usr/bin/env python3
"""Read-only MCP context server for Unsloth_Core."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("UCORE_PROJECT_ROOT", "/home/athar/Projects/Unsloth_Core")).resolve()

RESOURCES = {
    "ucore://project-context": ("Project Context", ".codex/references/project-context.md", "text/markdown"),
    "ucore://commands": ("Current Commands", ".codex/references/current-commands.md", "text/markdown"),
    "ucore://mcp-servers": ("MCP Servers", ".codex/references/mcp-servers.md", "text/markdown"),
    "ucore://agents": ("Agent Entrypoint", "AGENTS.md", "text/markdown"),
    "ucore://project-state": ("Project State", "docs/project-state.md", "text/markdown"),
    "ucore://strategy": ("NPC Production Strategy", "etc/npc-production-strategy.yaml", "text/yaml"),
    "ucore://dashboard-agents": (
        "Dashboard Agent Entrypoint",
        "src/dashboard/unity-npc-llm-training-dashboard/AGENTS.md",
        "text/markdown",
    ),
}

REFERENCE_NAMES = {
    "project-context": "ucore://project-context",
    "commands": "ucore://commands",
    "mcp-servers": "ucore://mcp-servers",
    "agents": "ucore://agents",
    "project-state": "ucore://project-state",
    "strategy": "ucore://strategy",
    "dashboard-agents": "ucore://dashboard-agents",
}


def _inside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def _read_repo_file(relative_path: str, limit: int = 24000) -> str:
    path = (ROOT / relative_path).resolve()
    if not _inside_root(path):
        raise ValueError(f"path escapes project root: {relative_path}")
    if not path.exists():
        return f"Missing: {relative_path}\n"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + "\n\n[truncated]\n"
    return text


def _resource_payload(uri: str) -> dict[str, Any]:
    if uri not in RESOURCES:
        raise KeyError(f"unknown resource: {uri}")
    _name, rel_path, mime_type = RESOURCES[uri]
    return {"uri": uri, "mimeType": mime_type, "text": _read_repo_file(rel_path)}


def _context_summary() -> str:
    agents = _read_repo_file("AGENTS.md", 16000)
    project_context = _read_repo_file(".codex/references/project-context.md", 16000)
    strategy = _read_repo_file("etc/npc-production-strategy.yaml", 12000)
    return "\n\n".join(
        [
            "# Unsloth_Core Context Summary",
            "Source precedence: live repo/tool output, AGENTS.md, .codex references, docs, .hermes/.agents, global memory.",
            "Active NPCs: history_guide, chef_assistant.",
            "Production rule: current approved grounded workflow; template is smoke/dev only.",
            "Known drift: docs/project-state.md still mentions NotebookLM preference, but AGENTS.md wins unless user updates policy.",
            "Local low-VRAM rule: check nvidia-smi and ollama ps before train/eval; qwen2.5:7b is local judge default.",
            "## AGENTS.md",
            agents,
            "## .codex Project Context",
            project_context,
            "## Strategy YAML",
            strategy,
        ]
    )


def _ok(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    try:
        if method == "initialize":
            return _ok(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": {"resources": {}, "tools": {}},
                    "serverInfo": {"name": "ucore-context", "version": "0.1.0"},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "resources/list":
            resources = [
                {
                    "uri": uri,
                    "name": name,
                    "description": f"Unsloth_Core {name.lower()}",
                    "mimeType": mime_type,
                }
                for uri, (name, _rel_path, mime_type) in RESOURCES.items()
            ]
            return _ok(request_id, {"resources": resources})
        if method == "resources/read":
            uri = params.get("uri", "")
            return _ok(request_id, {"contents": [_resource_payload(uri)]})
        if method == "tools/list":
            return _ok(
                request_id,
                {
                    "tools": [
                        {
                            "name": "ucore_context_summary",
                            "description": "Return compact read-only Unsloth_Core source-of-truth summary.",
                            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                        },
                        {
                            "name": "ucore_reference",
                            "description": "Read a named Unsloth_Core Codex reference.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "enum": sorted(REFERENCE_NAMES.keys()),
                                    }
                                },
                                "required": ["name"],
                                "additionalProperties": False,
                            },
                        },
                    ]
                },
            )
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "ucore_context_summary":
                text = _context_summary()
            elif name == "ucore_reference":
                ref_name = args.get("name")
                uri = REFERENCE_NAMES.get(ref_name)
                if uri is None:
                    raise KeyError(f"unknown reference: {ref_name}")
                text = _resource_payload(uri)["text"]
            else:
                raise KeyError(f"unknown tool: {name}")
            return _ok(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
        if method == "prompts/list":
            return _ok(request_id, {"prompts": []})
        return _error(request_id, -32601, f"method not found: {method}")
    except Exception as exc:  # Keep server alive and report MCP-friendly errors.
        return _error(request_id, -32000, str(exc))


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"parse error: {exc}")
        else:
            response = _handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
