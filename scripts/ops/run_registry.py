"""
scripts/ops/run_registry.py — Unified Pipeline Run Registry

Provides a single, append-only source of truth for all pipeline stage
invocations: dataset generation, sanitize, dataset_eval, train, export,
evaluate, and feedback loop.

Every pipeline run appends a record to .pipeline/runs.jsonl and creates a
per-run directory at .pipeline/runs/{run_id}/ containing:

  meta.json              — immutable run metadata (created once at start)
  workflow_hooks.jsonl   — step lifecycle events (WorkflowHookRecorder target)
  log_state.jsonl        — structured log_state() events
  stdout.log             — raw stdout captured by the frontend server

Usage (in a pipeline script main()):

    from scripts.ops.run_registry import RunRegistry, make_pipeline_run_id

    registry = RunRegistry()
    run_id = make_pipeline_run_id(npc_key="history_guide", stage="train", preset="fast-3b")
    run_dir = registry.start_run(
        run_id=run_id,
        npc_key="history_guide",
        stage="train",
        technique="template",
        spec_path="subjects/NPC_specs/history_guide.json",
        preset="fast-3b",
    )

    try:
        # ... pipeline work ...
        registry.complete_run(
            run_id,
            artifacts={"gguf": "exports/history_guide/history_guide-lora-f16.gguf"},
            metrics={"train_loss": 0.042, "num_examples": 118},
        )
    except Exception as exc:
        registry.error_run(run_id, error=type(exc).__name__, message=str(exc))
        raise
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Append-only index path. Runtime state — not version-controlled.
_DEFAULT_INDEX = PROJECT_ROOT / ".pipeline" / "runs.jsonl"

# Pipeline stages (canonical labels)
STAGES = frozenset(
    ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate", "feedback"]
)

# File-level lock so that concurrent imports share the same lock instance
_registry_lock = threading.Lock()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_pipeline_run_id(
    npc_key: str,
    stage: str,
    preset_or_technique: str = "default",
) -> str:
    """Generate a unique run ID for a pipeline stage invocation.

    Format: {YYYYMMDD}_{npc_key}_{stage}_{preset_or_technique}_{seq:03d}

    Sequential numbering is per (npc_key, stage, preset_or_technique) per day,
    based on existing entries in the .pipeline/runs/ directory.

    Examples:
        20260520_history_guide_train_fast-3b_001
        20260520_history_guide_dataset_eval_template_002
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    runs_dir = PROJECT_ROOT / ".pipeline" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{today}_{npc_key}_{stage}_{preset_or_technique}_"
    existing = list(runs_dir.glob(f"{prefix}*"))
    seq = len(existing) + 1
    return f"{prefix}{seq:03d}"


# ── RunRegistry ──────────────────────────────────────────────────────────────


class RunRegistry:
    """Append-only pipeline run index.

    Design principles:
    - Best-effort: every method swallows exceptions. The registry must never
      crash a pipeline stage.
    - Append-only: records are never mutated; start/complete/error events are
      separate JSONL lines sharing the same run_id.
    - Thread-safe: file writes are protected by a module-level lock.
    - Zero dependencies: only stdlib.
    """

    def __init__(self, index_path: str | Path | None = None) -> None:
        env_path = os.getenv("UCORE_PIPELINE_INDEX")
        self.index_path = Path(index_path or env_path or _DEFAULT_INDEX)

    # ── Public API ────────────────────────────────────────────────────────

    def start_run(
        self,
        *,
        run_id: str,
        npc_key: str,
        stage: str,
        technique: str | None = None,
        spec_path: str | Path | None = None,
        preset: str | None = None,
        entrypoint: str = "cli",
        frontend_job_id: str | None = None,
        **extra: Any,
    ) -> Path:
        """Append a 'start' record and create the per-run directory.

        Returns the run_dir Path. Creates:
            .pipeline/runs/{run_id}/meta.json
            .pipeline/runs/{run_id}/  (empty dir for hooks/logs)
        """
        run_dir = self._run_dir(run_id)
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            meta: dict[str, Any] = {
                "run_id": run_id,
                "npc_key": npc_key,
                "stage": stage,
                "technique": technique,
                "spec_path": str(spec_path) if spec_path else None,
                "preset": preset,
                "entrypoint": entrypoint,
                "frontend_job_id": frontend_job_id
                or os.getenv("UCORE_FRONTEND_JOB_ID"),
                "pid": os.getpid(),
                "run_dir": str(run_dir),
                **extra,
            }
            _safe_write_json(run_dir / "meta.json", meta)
        except Exception:
            pass  # Best-effort — still return the run_dir

        self._append(
            "start",
            run_id=run_id,
            npc_key=npc_key,
            stage=stage,
            technique=technique,
            spec_path=str(spec_path) if spec_path else None,
            preset=preset,
            entrypoint=entrypoint,
            frontend_job_id=frontend_job_id or os.getenv("UCORE_FRONTEND_JOB_ID"),
            pid=os.getpid(),
            run_dir=str(run_dir),
            **extra,
        )
        return run_dir

    def complete_run(
        self,
        run_id: str,
        *,
        artifacts: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        """Append a 'complete' record for the given run_id."""
        self._append(
            "complete",
            run_id=run_id,
            status="ok",
            artifacts=artifacts or {},
            metrics=metrics or {},
            **extra,
        )

    def error_run(
        self,
        run_id: str,
        *,
        error: str,
        message: str = "",
        **extra: Any,
    ) -> None:
        """Append an 'error' record for the given run_id."""
        self._append(
            "error",
            run_id=run_id,
            status="error",
            error=error,
            message=message,
            **extra,
        )

    def query(
        self,
        *,
        npc_key: str | None = None,
        stage: str | None = None,
        event: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Read and filter the run index.

        Returns records in chronological order (oldest first).
        All filters are ANDed together.
        """
        records = self._read_all()
        if npc_key:
            records = [r for r in records if r.get("npc_key") == npc_key]
        if stage:
            records = [r for r in records if r.get("stage") == stage]
        if event:
            records = [r for r in records if r.get("event") == event]
        return records[-limit:]

    def latest_run(
        self,
        npc_key: str,
        stage: str | None = None,
        *,
        status: str = "ok",
    ) -> dict | None:
        """Return the most recent 'complete' (or filtered status) record."""
        records = self._read_all()
        for r in reversed(records):
            if r.get("npc_key") != npc_key:
                continue
            if stage and r.get("stage") != stage:
                continue
            if r.get("event") != "complete":
                continue
            if status and r.get("status") != status:
                continue
            return r
        return None

    def npc_summary(self, npc_key: str) -> dict:
        """Compute a summary of all pipeline stages for an NPC.

        Returns a dict with the most recent complete run per stage and a
        computed pipeline_health label ('healthy' | 'partial' | 'error' | 'empty').
        """
        records = self._read_all()
        latest_complete: dict[str, dict] = {}
        latest_error: dict[str, dict] = {}

        for r in records:
            if r.get("npc_key") != npc_key:
                continue
            stage = r.get("stage", "")
            if r.get("event") == "complete":
                latest_complete[stage] = r
            elif r.get("event") == "error":
                latest_error[stage] = r

        core_stages = ["generate", "sanitize", "dataset_eval", "train", "export"]
        completed_core = sum(1 for s in core_stages if s in latest_complete)
        has_errors = bool(latest_error)

        if completed_core == len(core_stages):
            health = "healthy"
        elif completed_core > 0 and not has_errors:
            health = "partial"
        elif has_errors:
            health = "error"
        else:
            health = "empty"

        return {
            "npc_key": npc_key,
            "pipeline_health": health,
            "stages": {
                stage: {
                    "latest_complete": latest_complete.get(stage),
                    "latest_error": latest_error.get(stage),
                }
                for stage in sorted(STAGES)
            },
        }

    def hook_path(self, run_id: str) -> Path:
        """Return the canonical workflow_hooks.jsonl path for a run."""
        return self._run_dir(run_id) / "workflow_hooks.jsonl"

    def log_state_path(self, run_id: str) -> Path:
        """Return the canonical log_state.jsonl path for a run."""
        return self._run_dir(run_id) / "log_state.jsonl"

    # ── Private helpers ────────────────────────────────────────────────────

    def _run_dir(self, run_id: str) -> Path:
        return PROJECT_ROOT / ".pipeline" / "runs" / run_id

    def _append(self, event: str, **fields: Any) -> None:
        """Best-effort atomic JSONL append."""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            record: dict[str, Any] = {
                "ts": _iso_now(),
                "event": event,
                **{k: v for k, v in fields.items() if v is not None},
            }
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            with _registry_lock:
                with self.index_path.open("a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            pass  # Best-effort — never raise

    def _read_all(self) -> list[dict]:
        """Parse all records from the index file."""
        if not self.index_path.exists():
            return []
        records: list[dict] = []
        try:
            with self.index_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        return records


# ── Convenience context manager ──────────────────────────────────────────────


class PipelineRun:
    """Context manager that wraps RunRegistry.start_run / complete_run / error_run.

    Usage:
        with PipelineRun(npc_key="history_guide", stage="train", preset="fast-3b") as run:
            run.run_id    # the generated run ID
            run.run_dir   # Path to .pipeline/runs/{run_id}/
            # ... do pipeline work ...
            run.set_artifacts(gguf="exports/...")
            run.set_metrics(train_loss=0.042)
    """

    def __init__(
        self,
        *,
        npc_key: str,
        stage: str,
        technique: str | None = None,
        preset: str | None = None,
        spec_path: str | Path | None = None,
        entrypoint: str = "cli",
        frontend_job_id: str | None = None,
        registry: RunRegistry | None = None,
        run_id: str | None = None,
    ) -> None:
        self._registry = registry or RunRegistry()
        self.npc_key = npc_key
        self.stage = stage
        self.technique = technique
        self.preset = preset
        self.spec_path = spec_path
        self.entrypoint = entrypoint
        self.frontend_job_id = frontend_job_id
        self.run_id = run_id or make_pipeline_run_id(
            npc_key=npc_key,
            stage=stage,
            preset_or_technique=preset or technique or "default",
        )
        self.run_dir: Path = PROJECT_ROOT / ".pipeline" / "runs" / self.run_id
        self._artifacts: dict[str, Any] = {}
        self._metrics: dict[str, Any] = {}

    def __enter__(self) -> "PipelineRun":
        self.run_dir = self._registry.start_run(
            run_id=self.run_id,
            npc_key=self.npc_key,
            stage=self.stage,
            technique=self.technique,
            spec_path=self.spec_path,
            preset=self.preset,
            entrypoint=self.entrypoint,
            frontend_job_id=self.frontend_job_id,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            self._registry.complete_run(
                self.run_id,
                artifacts=self._artifacts,
                metrics=self._metrics,
            )
        else:
            self._registry.error_run(
                self.run_id,
                error=exc_type.__name__ if exc_type else "unknown",
                message=str(exc_val),
            )
        return False  # Never suppress exceptions

    def set_artifacts(self, **kwargs: Any) -> None:
        self._artifacts.update(kwargs)

    def set_metrics(self, **kwargs: Any) -> None:
        self._metrics.update(kwargs)

    @property
    def hook_path(self) -> Path:
        return self.run_dir / "workflow_hooks.jsonl"

    @property
    def log_state_path(self) -> Path:
        return self.run_dir / "log_state.jsonl"


# ── Standalone helpers ────────────────────────────────────────────────────────


def _safe_write_json(path: Path, data: Any) -> None:
    """Atomically write JSON to a file using a temp-rename pattern."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        tmp.rename(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def archive_quality_artifact(src: Path, run_id: str) -> Path | None:
    """Copy a quality artifact into a versioned history/ subdirectory.

    Usage:
        archive_quality_artifact(
            Path("subjects/datasets/history_guide/template/quality_summary.json"),
            run_id="20260520_history_guide_dataset_eval_template_001",
        )

    Returns the destination path, or None on failure.
    """
    if not src.exists():
        return None
    try:
        history_dir = src.parent / "history"
        history_dir.mkdir(exist_ok=True)
        stem = src.stem  # e.g. "quality_summary"
        dst = history_dir / f"{stem}_{run_id}{src.suffix}"
        import shutil
        shutil.copy2(src, dst)
        return dst
    except Exception:
        return None
