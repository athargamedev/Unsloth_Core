from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TYPE_CHECKING

from src.config.constants import DEFAULT_JUDGE_MODEL

if TYPE_CHECKING:
    from src.core.ops.pipeline_db import PipelineDB

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
    "sanitize": "dataset_clean",
    "training_pipeline": "adapter",
    "export_gguf": "gguf_adapter",
    "export_pipeline": "gguf_adapter",
    "export_adapter": "gguf_adapter",
    "export_full_merge": "gguf_full",
    "evaluate_model": "eval_report",
    "feedback_loop": "feedback_json",
    "deepeval_run": "quality_report",
    "evaluate_pipeline": "eval_report",
    "compare_models": "eval_report",
    "compare_runs": "eval_report",
    "write_report": "eval_report",
}


@dataclass
class StepContext:
    """Context object yielded by step() for intermediate diagnostic messages.

    Usage:
        with hook_recorder.step("train", ...) as ctx:
            ctx.log("Loading dataset...")
            ctx.log("Starting training loop...")
    """

    messages: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Record an intermediate diagnostic message for this step."""
        self.messages.append(message)


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
        # ── Chain linking ─────────────────────────────────────────────────
        self.base_event["workflow_id"] = os.getenv("WORKFLOW_ID")
        self.next_action: str | None = os.getenv("WORKFLOW_NEXT_ACTION")
        self.next_artifact: str | None = os.getenv("WORKFLOW_NEXT_ARTIFACT")
        _await_conf = os.getenv("WORKFLOW_AWAIT_CONFIRMATION", "")
        self.await_confirmation_stages: set[str] = {
            s.strip() for s in _await_conf.split(";") if s
        }

        # ── PipelineDB state ──────────────────────────────────────────
        self.db = db or create_pipeline_db()              # Auto-connect if caller didn't provide one
        self._db_run_created: bool = False                # NEW
        self._db_job_created: bool = False                # NEW
        self._db_job_uuid: str | None = None               # UUID of created job
        self._db_config_saved: bool = False                # pipeline_config_snapshots
        self._db_quality_gate_created: bool = False        # dataset_quality_gates
        self._db_eval_session_created: bool = False        # eval_sessions
        self._db_ephemeral_run_id: str | None = None       # evaluate_pipeline fallback run_id
        self._db_terminal_status: str | None = None        # cached terminal status for log-flush updates

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
        # ── Chain linking fields ────────────────────────────────────────────
        # Include next_action on any terminal status (complete/error)
        if status in ("complete", "error") and self.next_action and self.next_action != "NONE":
            event["next_action"] = self.next_action
        # Include next_artifact only on successful completion
        if status == "complete" and self.next_artifact:
            event["next_artifact"] = self.next_artifact
        # Signal confirmation gate when this step awaits operator go-ahead
        if status == "complete" and step in self.await_confirmation_stages:
            event["await_confirmation"] = True

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                json.dump(event, f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            # Hooks must never break the workflow; ignore all write errors.
            return

        # NEW: Also write to DB if a PipelineDB client is available
        if self.db is not None:
            try:
                if self.db.ensure_connected():
                    self._db_emit(step, status, fields)
            except Exception as e:
                # DB writes are best-effort — never break the pipeline
                logger.debug("DB emit failed for step=%s status=%s", step, status)

    @contextmanager
    def step(self, step: str, *, next_action: str | None = None, **fields: Any) -> Iterator[StepContext]:
        """Context manager for pipeline step lifecycle.

        Args:
            step: Name of the pipeline step.
            next_action: Override for the next-action value (defaults to
                WORKFLOW_NEXT_ACTION env var set at recorder creation time).
            **fields: Additional fields included in all events for this step.
        """
        ctx = StepContext()
        # Allow per-step override of next_action
        _prev_next_action = self.next_action
        if next_action is not None:
            self.next_action = next_action

        self.emit(step, "start", **fields)
        _start_time = time.monotonic()
        try:
            yield ctx
        except (Exception, SystemExit) as exc:
            duration_s = time.monotonic() - _start_time
            self.emit(step, "error", error=type(exc).__name__, message=str(exc), duration_s=duration_s, **fields)
            flush_logs = getattr(self, "_db_flush_logs", None)
            if callable(flush_logs):
                flush_logs(ctx.messages)
            raise
        else:
            duration_s = time.monotonic() - _start_time
            self.emit(step, "complete", duration_s=duration_s, **fields)
            flush_logs = getattr(self, "_db_flush_logs", None)
            if callable(flush_logs):
                flush_logs(ctx.messages)
        finally:
            if next_action is not None:
                self.next_action = _prev_next_action

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

        if step == "evaluate_pipeline" and not run_id:
            if self._db_ephemeral_run_id is None:
                self._db_ephemeral_run_id = f"evaluate_pipeline_{uuid.uuid4().hex}"
            run_id = self._db_ephemeral_run_id

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
        if status == "complete" and ("output_path" in fields or "output_dir" in fields):
            artifact_type = _ARTIFACT_TYPE_MAP.get(step)
            if artifact_type:
                self.db.create_artifact(
                    npc_key=npc_key,
                    artifact_type=artifact_type,
                    file_path=fields.get("output_path") or fields.get("output_dir", ""),
                    technique=technique_val,
                    run_id=run_id,
                )
 
        # ── CONFIG SNAPSHOT lifecycle ─────────────────────────────────
        if step == "training_pipeline" and status == "start" and not self._db_config_saved:
            full_config = {
                "preset": fields.get("preset"),
                "technique": technique_val,
                "output_dir": fields.get("output_dir"),
                "export_gguf": fields.get("export_gguf"),
                "run_id": run_id,
            }
            self.db.save_config_snapshot(
                npc_key=npc_key,
                full_config=full_config,
                preset=fields.get("preset"),
                technique=technique_val,
                file_path=fields.get("output_dir"),
            )
            self._db_config_saved = True
 
        # ── QUALITY GATE lifecycle ────────────────────────────────────
        if step == "deepeval_run" and status == "complete" and not self._db_quality_gate_created:
            # Try to read quality_summary.json from well-known path
            import json as _json
            from pathlib import Path as _Path
            qa_path = (
                _Path(f"subjects/datasets/{npc_key}/{technique_val}/quality_summary.json")
                if npc_key and technique_val else None
            )
            if qa_path and qa_path.exists():
                try:
                    with qa_path.open("r", encoding="utf-8") as _f:
                        qa_data = _json.load(_f)
                    self.db.create_quality_gate(
                        npc_key=npc_key,
                        technique=technique_val,
                        total_samples=qa_data.get("total", 0),
                        passed=qa_data.get("passed", 0),
                        failed=qa_data.get("failed", 0),
                        pass_rate=float(qa_data.get("pass_rate", 0.0)),
                        metrics=qa_data.get("metrics"),
                        categories=qa_data.get("categories"),
                        failures=qa_data.get("failures"),
                        judge_model=qa_data.get("judge_model", fields.get("judge_model", DEFAULT_JUDGE_MODEL)),
                        dataset_path=str(qa_path),
                    )
                except Exception as _exc:
                    logger.debug("Failed to read quality_summary.json: %s", _exc)
            else:
                # No file yet — record what we know from step fields
                self.db.create_quality_gate(
                    npc_key=npc_key,
                    technique=technique_val or "unknown",
                    total_samples=0,
                    passed=0,
                    failed=0,
                    pass_rate=0.0,
                    judge_model=fields.get("judge_model", DEFAULT_JUDGE_MODEL),
                )
            self._db_quality_gate_created = True
 
        # ── EVAL SESSION lifecycle ────────────────────────────────────
        if step == "evaluate_pipeline" and status == "complete" and not self._db_eval_session_created:
            # Read structured eval data from the feedback JSON file (written by evaluate.py)
            # rather than relying on step fields, which don't contain the comparison results.
            import json as _json
            from pathlib import Path as _Path

            feedback_path: str | None = None
            report_html = fields.get("report_path")
            fb_path_str = fields.get("feedback_json")

            # Try explicit feedback_json field first, then fall back to scanning report_dir/feedback/
            if fb_path_str:
                fb_candidate = _Path(fb_path_str)
                if fb_candidate.exists():
                    feedback_path = str(fb_candidate)
            if not feedback_path and report_html:
                fb_dir = _Path(report_html).parent / "feedback"
                if fb_dir.exists():
                    fb_files = sorted(fb_dir.glob("*.json"))
                    if fb_files:
                        feedback_path = str(fb_files[-1])

            # Extract structured data from the feedback JSON if available
            total_examples: int | None = None
            baseline_wins: int | None = None
            candidate_wins: int | None = None
            ties: int | None = None
            win_rate: float | None = None
            per_concept: dict | None = None
            weak_concepts: list | None = None

            if feedback_path:
                try:
                    with _Path(feedback_path).open("r", encoding="utf-8") as _f:
                        fb_data = _json.load(_f)
                    total_examples = fb_data.get("total_examples")
                    baseline_wins = fb_data.get("baseline_wins")
                    candidate_wins = fb_data.get("candidate_wins")
                    ties = fb_data.get("ties")
                    win_rate = fb_data.get("win_rate")
                    per_concept = fb_data.get("per_concept")
                    weak_concepts = fb_data.get("weak_concepts")
                except Exception as _exc:
                    logger.debug("Failed to read feedback JSON: %s", _exc)

            metadata = {
                "html": fields.get("html", False),
                "track": fields.get("track", False),
                "candidate_path": fields.get("candidate"),
                "baseline_path": fields.get("baseline"),
                "judge_model": fields.get("judge_model", DEFAULT_JUDGE_MODEL),
            }

            self.db.create_eval_session(
                npc_key=npc_key,
                report_html_path=report_html,
                feedback_json_path=feedback_path,
                total_examples=total_examples,
                baseline_wins=baseline_wins,
                candidate_wins=candidate_wins,
                ties=ties,
                win_rate=win_rate,
                per_concept=per_concept,
                weak_concepts=weak_concepts,
                metadata=metadata,
            )
            # Also update pipeline_jobs.loss with the eval win_rate
            if win_rate is not None and self._db_job_uuid:
                try:
                    self.db.update_job_status(self._db_job_uuid, loss=float(win_rate))
                except Exception as e:
                    pass

            self._db_eval_session_created = True

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
            preset = fields.get("preset") or fields.get("technique") or "default"
            self.db.create_run(
                npc_key=npc_key,
                run_id=run_id or f"{step}_{uuid.uuid4().hex}",
                run_dir=fields.get("output_dir", ""),
                preset=preset,
                model_id=fields.get("model"),
                technique=technique_val,
                spec_path=self.base_event.get("spec_path"),
                status=status,
            )
            self._db_run_created = True

        elif status in ("complete", "error") and self._db_run_created:
            resolved_status = "ok" if status == "complete" else "failed"
            metrics: dict[str, Any] = {"step": step}
            if "training_loss" in fields:
                metrics["loss"] = fields["training_loss"]
            if "num_examples" in fields:
                metrics["num_examples"] = fields["num_examples"]
            if "duration_s" in fields:
                metrics["duration_s"] = fields["duration_s"]
            metrics["status"] = resolved_status
            if status == "error":
                metrics["error"] = fields.get("error", "Unknown error")

            self.db.update_run_metrics(
                npc_key=npc_key,
                run_id=run_id or f"{step}_{uuid.uuid4().hex}",
                metrics=metrics,
                status=resolved_status,
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

            result = self.db.create_job(
                npc_key=npc_key,
                type=job_type,
                command_id=run_id or step,
                command_args=[npc_key, technique_val],
            )
            if result and "id" in result:
                self._db_job_uuid = result["id"]
                # Immediately mark as running to prevent the queue poller
                # (which polls WHERE status = 'pending' every 2s) from picking
                # up this job and trying to spawn npc_key as an executable.
                self.db.update_job_status(self._db_job_uuid, status="running")
            self._db_job_created = True

        elif status in ("complete", "error") and self._db_job_created and self._db_job_uuid:
            if status == "complete":
                self._db_terminal_status = "completed"
            elif status == "error":
                self._db_terminal_status = "failed"
            error_msg = fields.get("error") if status == "error" else None
            job_loss = fields.get("loss")
            kwargs = dict(
                status=self._db_terminal_status,
                error=error_msg,
            )
            if job_loss is not None:
                kwargs["loss"] = job_loss
            self.db.update_job_status(self._db_job_uuid, **kwargs)

    def _db_flush_logs(self, messages: list[str]) -> None:
        """Flush accumulated log messages to the pipeline_jobs.logs column.

        Called from step() on both complete and error paths so that
        intermediate ctx.log() calls are persisted to the database.
        """
        if not messages or not self.db or not self._db_job_uuid:
            return
        try:
            self.db.update_job_status(
                self._db_job_uuid,
                status=self._resolve_log_status(),
                logs=messages,
            )
        except Exception as e:
            # Best-effort — never break the pipeline
            pass

    def _resolve_log_status(self) -> str:
        """Return the current job status for log-flush updates.

        If the job was already completed or failed, keep that status so
        the log update doesn't overwrite the terminal state.
        """
        return self._db_terminal_status or "running"


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
        from src.core.ops.pipeline_db import PipelineDB  # noqa: PLC0415

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

    @staticmethod
    def group_by_trace(events: list[dict]) -> dict[str, list[dict]]:
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
            "traces": [cls.trace_summary(trace) for trace in cls.group_by_trace(events).values()],
        }

    @classmethod
    def pipeline_chain(cls, hook_path: str | Path) -> dict:
        """Analyze a pipeline hook file and return chain status.

        Filters events that carry a workflow_id (pipeline events), groups
        by step name, and resolves the latest status per step.

        Returns:
            workflow_id: shared workflow ID across all pipeline events (or None).
            stages: list of {step, status, duration_s, next_action, artifact_path}
            next_expected: name of the next step that should run, derived from
                the last completed step's next_action that hasn't been
                completed yet. None if all steps are done or no chain set.
            artifacts_ready: list of artifact paths from completed steps
                (next_artifact, output_path, or output_dir).
            awaiting_confirmation: True if any completed step has
                await_confirmation=true.
        """
        events = cls.read(hook_path)
        pipeline_events = [e for e in events if e.get("workflow_id")]

        empty = {
            "workflow_id": None,
            "stages": [],
            "next_expected": None,
            "artifacts_ready": [],
            "awaiting_confirmation": False,
        }
        if not pipeline_events:
            return empty

        workflow_id = pipeline_events[0].get("workflow_id")

        # Keep the latest event per step name (last write wins)
        step_map: dict[str, dict] = {}
        for event in pipeline_events:
            step_name: str = event.get("step", "?")
            step_map[step_name] = event

        # Build stage summaries from the resolved event per step
        stages: list[dict] = []
        for step_name, event in step_map.items():
            artifact_path = (
                event.get("next_artifact")
                or event.get("output_path")
                or event.get("output_dir")
            )
            stages.append({
                "step": step_name,
                "status": event.get("status", "?"),
                "duration_s": event.get("duration_s"),
                "next_action": event.get("next_action"),
                "artifact_path": artifact_path,
            })

        # Sort stages chronologically by their first event timestamp
        step_order: dict[str, str] = {}
        for event in pipeline_events:
            sn = event.get("step", "?")
            ts = event.get("ts", "")
            if sn not in step_order or ts < step_order[sn]:
                step_order[sn] = ts
        stages.sort(key=lambda s: step_order.get(s["step"], ""))

        # Derive next_expected: find the last completed step whose
        # next_action hasn't been fulfilled yet.
        next_expected: str | None = None
        completed_with_next = [
            s for s in stages
            if s["status"] == "complete" and s.get("next_action") and s["next_action"] != "NONE"
        ]
        for step_info in reversed(completed_with_next):
            expected = step_info["next_action"]
            already_done = any(
                s["step"] == expected and s["status"] == "complete"
                for s in stages
            )
            if not already_done:
                next_expected = expected
                break
        # If all next_actions are fulfilled, chain is complete
        if next_expected is None and completed_with_next:
            last_next = completed_with_next[-1]["next_action"]
            if any(s["step"] == last_next and s["status"] == "complete" for s in stages):
                next_expected = None  # entire pipeline is done
            else:
                next_expected = last_next

        # Collect artifact paths from completed steps
        artifacts_ready: list[str] = [
            s["artifact_path"] for s in stages
            if s["status"] == "complete" and s.get("artifact_path")
        ]

        # Check for confirmation gate signal
        awaiting_confirmation = any(
            e.get("await_confirmation") for e in pipeline_events
            if e.get("status") == "complete"
        )

        return {
            "workflow_id": workflow_id,
            "stages": stages,
            "next_expected": next_expected,
            "artifacts_ready": artifacts_ready,
            "awaiting_confirmation": awaiting_confirmation,
        }
