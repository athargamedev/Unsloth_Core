from __future__ import annotations

"""Canonical run artifact bundle helpers.

This module writes a stable per-run JSON bundle under .pipeline/runs/{run_id}/
so generation, sanitation, evaluation, and training all have one shared record
shape regardless of the stage-specific legacy files that still exist for
compatibility.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.ops.artifact_registry import record_stage_artifacts_best_effort

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CANONICAL_RUNS_ROOT = PROJECT_ROOT / ".pipeline" / "runs"


@dataclass(frozen=True)
class CanonicalArtifactBundle:
    run_id: str
    stage: str
    npc_key: str
    technique: str
    created_at: str
    artifacts: dict[str, Any]
    metrics: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_run_dir(run_id: str) -> Path:
    return CANONICAL_RUNS_ROOT / run_id


def canonical_bundle_path(run_id: str) -> Path:
    return canonical_run_dir(run_id) / "artifacts.json"


def write_canonical_bundle(bundle: CanonicalArtifactBundle) -> Path:
    path = canonical_bundle_path(bundle.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(asdict(bundle), f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    return path


def record_canonical_bundle(
    *,
    run_id: str,
    stage: str,
    npc_key: str,
    technique: str,
    artifacts: Mapping[str, Any],
    metrics: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    bundle = CanonicalArtifactBundle(
        run_id=run_id,
        stage=stage,
        npc_key=npc_key,
        technique=technique,
        created_at=_iso_now(),
        artifacts=dict(artifacts),
        metrics=dict(metrics) if metrics is not None else None,
        metadata=dict(metadata) if metadata is not None else None,
    )
    path = write_canonical_bundle(bundle)
    record_stage_artifacts_best_effort(
        run_id,
        npc_key,
        stage,
        artifacts,
        technique=technique,
        metadata={**(metadata or {}), "canonical_bundle": str(path)},
    )
    return path
