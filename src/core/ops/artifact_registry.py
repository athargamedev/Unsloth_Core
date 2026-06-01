#!/usr/bin/env python3
"""Append-only artifact registry for Unsloth_Core pipeline outputs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_ARTIFACT_INDEX = PROJECT_ROOT / ".pipeline" / "artifacts.jsonl"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class ArtifactRegistry:
    """Small JSONL index for stage outputs.

    Records enough context to answer: what artifact exists, from which run/stage,
    for which NPC/technique, and with which checksum.
    """

    def __init__(self, index_path: str | Path | None = None) -> None:
        self.index_path = Path(index_path or DEFAULT_ARTIFACT_INDEX)

    def record_artifact(
        self,
        run_id: str,
        npc_key: str,
        stage: str,
        artifact_type: str,
        path: str | Path,
        *,
        technique: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_path = Path(path)
        exists = artifact_path.exists()
        record: dict[str, Any] = {
            "ts": _iso_now(),
            "run_id": run_id,
            "npc_key": npc_key,
            "stage": stage,
            "artifact_type": artifact_type,
            "path": str(artifact_path),
            "technique": technique,
            "exists": exists,
            "size_bytes": artifact_path.stat().st_size if exists and artifact_path.is_file() else None,
            "sha256": _sha256(artifact_path),
            "metadata": metadata or {},
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in record.items() if v is not None}, ensure_ascii=False, default=str) + "\n")
        return record

    def query(
        self,
        *,
        npc_key: str | None = None,
        artifact_type: str | None = None,
        stage: str | None = None,
        technique: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        records = self._read_all()
        if npc_key:
            records = [r for r in records if r.get("npc_key") == npc_key]
        if artifact_type:
            records = [r for r in records if r.get("artifact_type") == artifact_type]
        if stage:
            records = [r for r in records if r.get("stage") == stage]
        if technique:
            records = [r for r in records if r.get("technique") == technique]
        return records[-limit:]

    def latest_artifact(
        self,
        npc_key: str,
        artifact_type: str,
        *,
        technique: str | None = None,
        must_exist: bool = True,
    ) -> dict[str, Any] | None:
        for record in reversed(self.query(npc_key=npc_key, artifact_type=artifact_type, technique=technique, limit=10_000)):
            if must_exist and not Path(str(record.get("path", ""))).exists():
                continue
            return record
        return None

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records


def record_stage_artifacts(
    registry: ArtifactRegistry,
    run_id: str,
    npc_key: str,
    stage: str,
    artifacts: Mapping[str, str | Path | list[str] | list[Path] | None],
    *,
    technique: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Record canonical ArtifactRegistry entries from legacy stage artifact maps."""
    stage_map: dict[str, list[tuple[str, str]]] = {
        "generate": [("dataset_raw", "train"), ("dataset_raw", "train_path")],
        "sanitize": [("dataset_clean", "output"), ("dataset_clean", "clean_path")],
        "dataset_eval": [("quality_summary", "quality_summary"), ("quality_summary", "summary_path")],
        "train": [("adapter_checkpoint", "run_dir"), ("adapter_checkpoint", "output_dir")],
        "export": [("gguf_adapter", "gguf"), ("gguf_adapter", "gguf_path"), ("gguf_adapter", "output"), ("gguf_adapter", "gguf_files")],
        "evaluate": [("eval_index", "eval_index"), ("eval_index", "index_path")],
    }
    records: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for artifact_type, key in stage_map.get(stage, []):
        if artifact_type in seen_types:
            continue
        value = artifacts.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            continue
        records.append(
            registry.record_artifact(
                run_id=run_id,
                npc_key=npc_key,
                stage=stage,
                artifact_type=artifact_type,
                path=value,
                technique=technique,
                metadata=metadata,
            )
        )
        seen_types.add(artifact_type)
    return records


def record_stage_artifacts_best_effort(
    run_id: str,
    npc_key: str,
    stage: str,
    artifacts: Mapping[str, str | Path | list[str] | list[Path] | None],
    *,
    technique: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort production wrapper; never blocks pipeline work."""
    try:
        record_stage_artifacts(
            ArtifactRegistry(),
            run_id,
            npc_key,
            stage,
            artifacts,
            technique=technique,
            metadata=metadata,
        )
    except Exception:
        pass
