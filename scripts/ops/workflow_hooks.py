from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.ops.pipeline_db import PipelineDB

logger = logging.getLogger(__name__)

# ── Artifact type mapping ────────────────────────────────────────────────
# Maps pipeline step names to the CHECK constraint values in
# pipeline_artifacts.artifact_type. Unknown steps are silently skipped.
_ARTIFACT_TYPE_MAP: dict[str, str] = {
    "generate_dataset": "dataset_raw",
    "prepare": "dataset_raw",
    "generate_examples": "dataset_raw",
    "write_artifacts": "dataset_clean",
    "sanitize_dataset": "dataset_clean",
    "training_pipeline": "adapter",
    "export_gguf": "gguf_adapter",
    "export_pipeline": "gguf_adapter",
    "evaluate_model": "eval_report",
    "feedback_loop": "feedback_json",
}


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
        db: PipelineDB | None = None,                    # NEW: optional DB client
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
        # ── PipelineDB state ──────────────────────────────────────────
        self.db = db or create_pipeline_db()              # Auto-connect if caller didn't provide one
        self._db_run_created: bool = False                # NEW
        self._db_job_created: bool = False                # NEW

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

        # NEW: Also write to DB if a PipelineDB client is available
        if self.db is not None:
            try:
                if self.db.ensure_connected():
                    self._db_emit(step, status, fields)
            except Exception:
                # DB writes are best-effort — never break the pipeline
                logger.debug("DB emit failed for step=%s status=%s", step, status)

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

    # ── PipelineDB integration ─────────────────────────────────────────

    def _db_emit(self, step: str, status: str, fields: dict[str, Any]) -> None:
        """Map a hook event to PipelineDB calls for Supabase persistence.

        Called from emit() when a PipelineDB client is available and
        connected. All exceptions are swallowed — this must never block
        the pipeline.
        """
        # Resolve identity fields: explicit event-level values override base
        npc_key = fields.get("npc_key") or self.base_event.get("npc_key")
        run_id = fields.get("run_id") or self.base_event.get("run_id")
        technique_val = fields.get("technique") or self.base_event.get("technique")

        if not npc_key:
            return  # Cannot write to DB without an NPC key

        # ── RUN lifecycle ─────────────────────────────────────────────
        # All pipeline scripts fire step() events. The FIRST "start" event
        # creates a pipeline_runs row, and subsequent "complete"/"error"
        # events update it. This works universally without a hardcoded
        # step-name allowlist.
        if status == "start" or status in ("complete", "error"):
            self._db_emit_run(npc_key, run_id, technique_val, step, status, fields)

        # ── JOB lifecycle (for frontend job queue tracking) ───────────
        self._db_emit_job(npc_key, run_id, technique_val, step, status, fields)

        # ── ARTIFACT lifecycle ────────────────────────────────────────
        if status == "complete" and "output_path" in fields:
            artifact_type = _ARTIFACT_TYPE_MAP.get(step)
            if artifact_type:
                self.db.create_artifact(
                    npc_key=npc_key,
                    artifact_type=artifact_type,
                    file_path=fields["output_path"],
                    technique=technique_val,
                    run_id=run_id,
                )

    def _db_emit_run(
        self,
        npc_key: str,
        run_id: str | None,
        technique_val: str | None,
        step: str,
        status: str,
        fields: dict[str, Any],
    ) -> None:
        """Handle pipeline_runs lifecycle events."""
        if status == "start" and not self._db_run_created:
            self.db.create_run(
                npc_key=npc_key,
                run_id=run_id or step,
                run_dir=fields.get("output_dir", ""),
                preset=fields.get("preset"),
                model_id=fields.get("model"),
                technique=technique_val,
                spec_path=self.base_event.get("spec_path"),
            )
            self._db_run_created = True

        elif status in ("complete", "error") and self._db_run_created:
            metrics: dict[str, Any] = {"step": step}
            if "training_loss" in fields:
                metrics["loss"] = fields["training_loss"]
            if "num_examples" in fields:
                metrics["num_examples"] = fields["num_examples"]
            if "duration_s" in fields:
                metrics["duration_s"] = fields["duration_s"]
            metrics["status"] = "ok" if status == "complete" else "failed"
            if status == "error":
                metrics["error"] = fields.get("error", "Unknown error")

            self.db.update_run_metrics(
                npc_key=npc_key,
                run_id=run_id or step,
                metrics=metrics,
            )

    def _db_emit_job(
        self,
        npc_key: str,
        run_id: str | None,
        technique_val: str | None,
        step: str,
        status: str,
        fields: dict[str, Any],
    ) -> None:
        """Handle pipeline_jobs lifecycle events."""
        job_id = run_id or self.base_event.get("run_id")

        if status == "start" and not self._db_job_created:
            # Map step to job type
            job_type = "Pipeline"
            if "training" in step or step in ("run_training", "training_pipeline"):
                job_type = "Training"
            elif "dataset" in step or step in ("generate_examples", "prepare", "write_artifacts", "sanitize", "deepeval_run", "sanitize_dataset"):
                job_type = "Dataset"
            elif "eval" in step or step in ("evaluate_pipeline", "compare_runs", "quick_eval", "evaluate_baseline", "evaluate_candidate"):
                job_type = "Evaluation"
            elif "export" in step:
                job_type = "Export"
            elif "feedback" in step or step == "feedback_loop":
                job_type = "Feedback"

            self.db.create_job(
                npc_key=npc_key,
                type=job_type,
                command_id=run_id or step,
                command_args=[npc_key, technique_val],
            )
            self._db_job_created = True

        elif status in ("complete", "error") and self._db_job_created and job_id:
            error_msg = fields.get("error") if status == "error" else None
            self.db.update_job_status(
                job_id,
                status="completed" if status == "complete" else "failed",
                error=error_msg,
            )


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


def create_pipeline_db() -> PipelineDB | None:
    """Create and return a connected PipelineDB instance, or None.

    Checks environment variables in order:
        1. SUPABASE_DB_URL
        2. PIPELINE_DB_URL
        3. Local Supabase defaults (postgres:postgres@127.0.0.1:15434)

    Returns None when no database is available (no env vars, no local
    Supabase, or psycopg2 not installed). Callers are expected to handle
    None gracefully.
    """
    try:
        from scripts.ops.pipeline_db import PipelineDB  # noqa: PLC0415

        db = PipelineDB()
        if db.ensure_connected():
            logger.info("PipelineDB connected for workflow hooks")
            return db
        logger.info("PipelineDB not available — hooks will write JSONL only")
    except Exception as exc:
        logger.debug("Failed to create PipelineDB: %s", exc)
    return None


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
