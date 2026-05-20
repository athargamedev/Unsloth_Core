from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


class WorkflowHookRecorder:
    """Best-effort JSONL hook recorder for pipeline step tracing."""

    def __init__(
        self,
        hook_path: str | Path | None,
        *,
        tool: str,
        npc_key: str | None = None,
        technique: str | None = None,
        spec_path: str | None = None,
    ) -> None:
        env_path = os.getenv("WORKFLOW_HOOKS_PATH")
        path = hook_path or env_path
        self.path = Path(path) if path else None
        self.base_event: dict[str, Any] = {
            "tool": tool,
            "npc_key": npc_key,
            "technique": technique,
            "spec_path": spec_path,
        }

    def emit(self, step: str, status: str, **fields: Any) -> None:
        if not self.path:
            return
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "status": status,
            **{k: v for k, v in self.base_event.items() if v is not None},
            **fields,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                json.dump(event, f, ensure_ascii=False)
                f.write("\n")
        except Exception:
            # Hooks must never break the workflow; ignore all write errors.
            return

    @contextmanager
    def step(self, step: str, **fields: Any) -> Iterator[None]:
        self.emit(step, "start", **fields)
        try:
            yield
        except Exception as exc:
            self.emit(step, "error", error=type(exc).__name__, message=str(exc), **fields)
            raise
        else:
            self.emit(step, "complete", **fields)


def default_hook_path(output_dir: str | Path, filename: str = "workflow_hooks.jsonl") -> Path:
    return Path(output_dir) / filename
