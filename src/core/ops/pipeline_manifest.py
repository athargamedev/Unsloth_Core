#!/usr/bin/env python3
"""
scripts/ops/pipeline_manifest.py — Centralized Pipeline Run Manifest

Tracks every pipeline stage (generate, sanitize, dataset-eval, train, export,
evaluate, feedback) in a single JSON manifest file at ``var/.pipeline/run_manifest.json``.
Replaces ad-hoc artifact tracking with a unified, queryable record.

Usage (simple one-shot integration from any pipeline script)::

    from src.core.ops.pipeline_manifest import record_pipeline_stage

    record_pipeline_stage("generate", "completed",
        artifacts={"dataset": "data/datasets/history_guide/template/train.jsonl"},
        metadata={"num_examples": 72},
    )

Usage (long-lived manifest for coordinated pipelines)::

    from src.core.ops.pipeline_manifest import PipelineManifest

    m = PipelineManifest("run_20260531_110000", "history_guide", "template", "fast-3b")
    m.record_stage("generate", "completed",
        artifacts={"dataset": "data/datasets/history_guide/template/train.jsonl"})
    m.save()

    # Later — load and inspect
    m2 = PipelineManifest.load()
    if m2 and m2.next_expected_stage() == "train":
        ...
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.paths import pipeline_root

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

MANIFEST_VERSION = "1.0"
MANIFEST_FILENAME = "run_manifest.json"
MANIFEST_TEMP_SUFFIX = ".tmp"

_DEFAULT_MANIFEST_PATH = pipeline_root() / MANIFEST_FILENAME

# Canonical pipeline stage order
_PIPELINE_ORDER: list[str] = [
    "spec",
    "preflight",
    "generate",
    "sanitize",
    "dataset_eval",
    "train",
    "export",
    "evaluate",
    "feedback",
]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


# ── Data Classes ───────────────────────────────────────────────────────────────


@dataclass
class StageRecord:
    """A single stage entry within a pipeline run manifest.

    Attributes mirror the JSON structure exactly so ``to_dict()`` / ``from_dict()``
    are straightforward transforms.
    """

    stage: str
    status: str  # "running" | "completed" | "failed" | "skipped"
    started_at: str  # ISO 8601
    completed_at: str | None = None  # ISO 8601
    duration_s: float | None = None
    exit_code: int | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
        }
        # Only include non-None / non-empty fields to keep the manifest clean.
        if self.completed_at is not None:
            d["completed_at"] = self.completed_at
        if self.duration_s is not None:
            d["duration_s"] = self.duration_s
        if self.exit_code is not None:
            d["exit_code"] = self.exit_code
        if self.artifacts:
            d["artifacts"] = self.artifacts
        if self.metadata:
            d["metadata"] = self.metadata
        if self.error is not None:
            d["error"] = self.error
        return d

    @staticmethod
    def from_dict(data: dict[str, Any]) -> StageRecord:
        return StageRecord(
            stage=data["stage"],
            status=data["status"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            duration_s=data.get("duration_s"),
            exit_code=data.get("exit_code"),
            artifacts=data.get("artifacts", {}),
            metadata=data.get("metadata", {}),
            error=data.get("error"),
        )


# ── Manifest ───────────────────────────────────────────────────────────────────


class PipelineManifest:
    """Unified, queryable record of a single pipeline run.

    Reads from and writes to ``.pipeline/run_manifest.json`` atomically.
    Manifests are self-healing — missing directories and missing files are
    handled gracefully on first write.
    """

    def __init__(
        self,
        run_id: str,
        npc_key: str,
        technique: str,
        preset: str | None = None,
        *,
        manifest_path: str | Path | None = None,
    ) -> None:
        self.manifest_version: str = MANIFEST_VERSION
        self.run_id: str = run_id
        self.npc_key: str = npc_key
        self.technique: str = technique
        self.preset: str | None = preset
        self.created_at: str = _iso_now()
        self.updated_at: str = self.created_at
        self.stages: list[dict[str, Any]] = []

        path = manifest_path or os.getenv("UCORE_MANIFEST_PATH") or _DEFAULT_MANIFEST_PATH
        self._path: Path = Path(path)

    # ── Factory / Load ─────────────────────────────────────────────────────

    @staticmethod
    def load(
        manifest_path: str | Path | None = None,
    ) -> PipelineManifest | None:
        """Load the manifest from ``.pipeline/run_manifest.json``.

        Returns ``None`` when the file does not exist (caller decides how to
        handle a missing manifest — either initialise a new one or skip).
        Raises on malformed JSON.
        """
        path = Path(manifest_path or os.getenv("UCORE_MANIFEST_PATH") or _DEFAULT_MANIFEST_PATH)

        if not path.is_file():
            return None

        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        obj = PipelineManifest(
            run_id=raw["run_id"],
            npc_key=raw["npc_key"],
            technique=raw["technique"],
            preset=raw.get("preset"),
            manifest_path=path,
        )
        obj.manifest_version = raw.get("manifest_version", MANIFEST_VERSION)
        obj.created_at = raw.get("created_at", obj.created_at)
        obj.updated_at = raw.get("updated_at", obj.updated_at)
        obj.stages = raw.get("stages", [])
        return obj

    @staticmethod
    def resolve_run_id() -> str:
        """Return ``WORKFLOW_ID`` env var if set, else generate a fresh id.

        Generated format: ``run_YYYYMMDD_HHMMSS``.
        """
        workflow_id = os.getenv("WORKFLOW_ID")
        if workflow_id:
            return workflow_id
        run_id = os.getenv("RUN_ID")
        if run_id:
            return run_id
        now = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"run_{now}"

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    # ── Stage Recording ────────────────────────────────────────────────────

    def record_stage(
        self,
        stage: str,
        status: str,
        *,
        artifacts: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Append or update a stage record.

        If a record for *stage* already exists, it is updated in-place (no
        duplicate entries).  The call sets ``completed_at`` and ``duration_s``
        when *status* is ``"completed"``, ``"failed"``, or ``"skipped"``.

        Returns the record dict so callers can inspect the result.
        """
        now = _iso_now()

        # Find existing record by stage name
        existing = None
        for rec in self.stages:
            if rec["stage"] == stage:
                existing = rec
                break

        if existing is not None:
            # Update existing record — preserve started_at, update the rest.
            existing["status"] = status
            existing["completed_at"] = (
                now
                if status in ("completed", "failed", "skipped")
                else existing.get("completed_at")
            )
            if status in ("completed", "failed", "skipped"):
                started = existing.get("started_at", now)
                existing["duration_s"] = _duration_seconds(started, now)
                if status == "failed":
                    existing["exit_code"] = existing.get("exit_code", 1)
            if artifacts is not None:
                existing["artifacts"] = artifacts
            if metadata is not None:
                existing["metadata"] = metadata
            if error is not None:
                existing["error"] = error
            result = existing
        else:
            # New record
            started_at = now
            completed_at = now if status in ("completed", "failed", "skipped") else None
            duration_s = 0.0 if completed_at else None
            exit_code: int | None = None
            if status == "failed":
                exit_code = 1
            if completed_at:
                duration_s = _duration_seconds(started_at, completed_at)

            record: dict[str, Any] = {
                "stage": stage,
                "status": status,
                "started_at": started_at,
            }
            if completed_at is not None:
                record["completed_at"] = completed_at
            if duration_s is not None:
                record["duration_s"] = duration_s
            if exit_code is not None:
                record["exit_code"] = exit_code
            if artifacts:
                record["artifacts"] = artifacts
            if metadata:
                record["metadata"] = metadata
            if error is not None:
                record["error"] = error

            self.stages.append(record)
            result = record

        self.updated_at = _iso_now()
        return result

    # ── Persistence ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Full manifest as a JSON-serializable dict."""
        return {
            "manifest_version": self.manifest_version,
            "run_id": self.run_id,
            "npc_key": self.npc_key,
            "technique": self.technique,
            "preset": self.preset,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stages": self.stages,
        }

    def save(self) -> None:
        """Write manifest atomically to disk.

        Writes to a ``.tmp`` sibling first then renames — guarantees readers
        never see a partially-written file.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._path.with_suffix(self._path.suffix + MANIFEST_TEMP_SUFFIX)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            f.write("\n")

        os.replace(tmp_path, self._path)

    # ── Queries ────────────────────────────────────────────────────────────

    def stage_summary(self, stage: str) -> dict[str, Any] | None:
        """Return the record dict for *stage*, or ``None`` if it hasn't run."""
        for rec in self.stages:
            if rec["stage"] == stage:
                return rec
        return None

    def last_completed_stage(self) -> str | None:
        """Return the stage name of the last completed stage.

        Scans the ordered pipeline order — returns the latest entry that
        has status ``"completed"``.
        """
        candidate: str | None = None
        for stage_name in _PIPELINE_ORDER:
            rec = self.stage_summary(stage_name)
            if rec is not None and rec.get("status") == "completed":
                candidate = stage_name
        return candidate

    def next_expected_stage(self) -> str | None:
        """Return the next stage that hasn't run yet.

        Walks the canonical pipeline order starting after the last completed
        stage.  If all stages have run (or the current stage is still running),
        returns ``None``.

        This correctly handles early stages that were intentionally skipped:
        if ``preflight`` completed but ``spec`` was never recorded, the method
        returns ``generate`` (the first unrecorded stage *after* preflight),
        not ``spec``.
        """
        last = self.last_completed_stage()
        start_index = 0
        if last is not None:
            try:
                start_index = _PIPELINE_ORDER.index(last) + 1
            except ValueError:
                start_index = 0

        for i in range(start_index, len(_PIPELINE_ORDER)):
            stage_name = _PIPELINE_ORDER[i]
            rec = self.stage_summary(stage_name)
            if rec is None:
                return stage_name
            if rec.get("status") == "running":
                return stage_name
            if rec.get("status") not in ("completed", "skipped"):
                return stage_name

        # Everything has completed, is skipped, or we're past the last stage.
        return None

    @staticmethod
    def pipeline_order() -> list[str]:
        """Return the canonical ordering of pipeline stages."""
        return list(_PIPELINE_ORDER)


# ── Internal helpers ───────────────────────────────────────────────────────────


def _duration_seconds(start_iso: str, end_iso: str) -> float:
    """Difference between two ISO 8601 timestamps in fractional seconds.

    Returns 0.0 on any parse error (best-effort).
    """
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        return (end - start).total_seconds()
    except (ValueError, TypeError):
        return 0.0


# ── One-shot integration helper ────────────────────────────────────────────────


def record_pipeline_stage(
    stage: str,
    status: str = "completed",
    *,
    artifacts: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    """One-shot helper: load or create manifest, record a stage, save.

    Reads environment variables for context:

    * ``NPC_KEY`` (required — if unset, the call is a no-op and returns ``None``)
    * ``TECHNIQUE`` (optional, defaults to ``"unknown"``)
    * ``PRESET`` (optional)
    * ``WORKFLOW_ID`` or ``RUN_ID`` (optional, auto-generated if missing)

    This is designed for simple integration into pipeline scripts where only a
    single stage is being recorded.
    """
    npc_key = os.getenv("NPC_KEY")
    if not npc_key:
        logger.debug("record_pipeline_stage: NPC_KEY not set — skipping manifest write")
        return None

    technique = os.getenv("TECHNIQUE", "unknown")
    preset = os.getenv("PRESET")
    run_id = PipelineManifest.resolve_run_id()

    manifest_path = Path(os.getenv("UCORE_MANIFEST_PATH") or _DEFAULT_MANIFEST_PATH)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Acquire an exclusive file lock around the entire load-modify-save cycle.
    # This prevents TOCTOU races when two concurrent pipeline stages call
    # record_pipeline_stage() at the same time.
    # 'a+' creates the file if it doesn't exist and opens it for read+write
    # without truncating existing content. After truncating the file to make
    # it empty, all writes naturally land at position 0 (the new end-of-file).
    with open(manifest_path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            content = f.read().strip()

            if content:
                raw = json.loads(content)
                manifest = PipelineManifest(
                    run_id=raw.get("run_id", run_id),
                    npc_key=raw.get("npc_key", npc_key),
                    technique=raw.get("technique", technique),
                    preset=raw.get("preset", preset),
                    manifest_path=manifest_path,
                )
                manifest.manifest_version = raw.get("manifest_version", MANIFEST_VERSION)
                manifest.created_at = raw.get("created_at", manifest.created_at)
                manifest.updated_at = raw.get("updated_at", manifest.updated_at)
                manifest.stages = raw.get("stages", [])
            else:
                manifest = PipelineManifest(
                    run_id, npc_key, technique, preset, manifest_path=manifest_path
                )

            result = manifest.record_stage(
                stage, status, artifacts=artifacts, metadata=metadata, error=error
            )

            # Write back through the locked fd — safe because we hold the lock.
            f.seek(0)
            f.truncate()
            json.dump(manifest.to_dict(), f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    return result
