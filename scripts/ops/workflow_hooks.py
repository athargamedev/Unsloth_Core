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
        run_id: str | None = None,
    ) -> None:
        env_path = os.getenv("WORKFLOW_HOOKS_PATH")
        path = hook_path or env_path
        self.path = Path(path) if path else None
        self.base_event: dict[str, Any] = {
            "tool": tool,
            "npc_key": npc_key,
            "technique": technique,
            "spec_path": spec_path,
            "run_id": run_id,
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
        except (Exception, SystemExit) as exc:
            self.emit(step, "error", error=type(exc).__name__, message=str(exc), **fields)
            raise
        else:
            self.emit(step, "complete", **fields)

def default_hook_path(
    output_dir: str | Path,
    filename: str = "workflow_hooks.jsonl",
    run_dir: str | Path | None = None
) -> Path:
    """Return the path to the workflow hooks JSONL file.

    If run_dir is provided (preferred), the hooks are written to the unified
    .pipeline/runs/{run_id}/ directory. Otherwise, they fall back to output_dir.
    """
    if run_dir:
        return Path(run_dir) / filename
    return Path(output_dir) / filename
class WorkflowHookReader:
    """Read and aggregate workflow hook JSONL files for dashboard display."""

    @staticmethod
    def read(hook_path: str | Path) -> list[dict]:
        """Parse a workflow_hooks.jsonl into a list of event dicts."""
        path = Path(hook_path)
        if not path.exists():
            return []
        events: list[dict] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events

    def group_by_trace(self, events: list[dict]) -> dict[str, list[dict]]:
        """Group events into traces by (tool, npc_key) sorted chronologically.

        A 'trace' is a sequence of events from the same tool + npc_key combination,
        ordered by timestamp. Returns {trace_key: [events]}.
        """
        traces: dict[str, list[dict]] = {}
        for event in events:
            tool = event.get("tool", "unknown")
            npc_key = event.get("npc_key", "unknown")
            key = f"{tool}:{npc_key}"
            traces.setdefault(key, []).append(event)
        # Sort each trace by timestamp
        for key in traces:
            traces[key].sort(key=lambda e: e.get("ts", ""))
        return traces

    @staticmethod
    def trace_summary(trace: list[dict]) -> dict:
        """Compute summary for a single trace (one tool + npc_key run).

        Returns:
            tool, npc_key, technique: from first event
            steps: list of {step, status, ts, duration_s, ...}
            start_ts, end_ts: overall time range
            total_duration_s: elapsed time
            completed: count of completed steps
            failed: count of failed steps
            events_by_step: {step: {start: event, complete: event, error: event}}
        """
        if not trace:
            return {}
        first = trace[0]
        last = trace[-1]
        steps: dict[str, dict[str, dict]] = {}
        for event in trace:
            step = event.get("step", "?")
            status = event.get("status", "?")
            steps.setdefault(step, {})[status] = event

        start_ts = first.get("ts", "")
        end_ts = last.get("ts", "")
        total_duration_s: float | None = None
        try:
            s = datetime.fromisoformat(start_ts) if start_ts else None
            e = datetime.fromisoformat(end_ts) if end_ts else None
            if s and e:
                total_duration_s = (e - s).total_seconds()
        except (ValueError, TypeError):
            pass

        step_list: list[dict] = []
        for step_name, events_by_status in steps.items():
            start_event = events_by_status.get("start", {})
            complete_event = events_by_status.get("complete", {})
            error_event = events_by_status.get("error", {})
            step_start_ts = start_event.get("ts", "")
            step_end_ts = complete_event.get("ts", "") or error_event.get("ts", "")
            step_duration_s: float | None = None
            try:
                ss = datetime.fromisoformat(step_start_ts) if step_start_ts else None
                se = datetime.fromisoformat(step_end_ts) if step_end_ts else None
                if ss and se:
                    step_duration_s = (se - ss).total_seconds()
            except (ValueError, TypeError):
                pass

            step_list.append({
                "step": step_name,
                "status": "complete" if complete_event else ("error" if error_event else "started"),
                "ts": step_start_ts or step_end_ts,
                "duration_s": step_duration_s,
                "has_start": bool(start_event),
                "has_complete": bool(complete_event),
                "has_error": bool(error_event),
            })

        completed = sum(1 for s in step_list if s["status"] == "complete")
        failed = sum(1 for s in step_list if s["status"] == "error")

        return {
            "tool": first.get("tool"),
            "npc_key": first.get("npc_key"),
            "technique": first.get("technique"),
            "spec_path": first.get("spec_path"),
            "run_id": first.get("run_id"),
            "start_ts": start_ts,
            "end_ts": end_ts,
            "total_duration_s": total_duration_s,
            "step_count": len(step_list),
            "completed": completed,
            "failed": failed,
            "steps": sorted(step_list, key=lambda s: s["ts"]),
            "events_by_step": steps,
        }

    @classmethod
    def pipeline_summary(cls, hook_path: str | Path) -> dict:
        """Read a hook file and return full summaries per trace.

        Returns {total_events: int, traces: list[dict]}.
        """
        events = cls.read(hook_path)
        return {
            "total_events": len(events),
            "traces": [cls.trace_summary(trace) for trace in cls().group_by_trace(events).values()],
        }
