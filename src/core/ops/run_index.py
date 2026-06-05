from __future__ import annotations

"""Canonical run index helpers for .pipeline/runs and legacy compatibility."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CANONICAL_RUNS_ROOT = PROJECT_ROOT / ".pipeline" / "runs"
CANONICAL_INDEX_PATH = PROJECT_ROOT / ".pipeline" / "runs_index.jsonl"


@dataclass(frozen=True)
class RunIndexEntry:
    run_id: str
    stage: str
    npc_key: str
    technique: str
    bundle_path: str
    created_at: str
    metrics: dict[str, Any] | None = None
    artifacts: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def iter_canonical_run_bundle_paths(root: Path | None = None) -> list[Path]:
    base = root or CANONICAL_RUNS_ROOT
    if not base.exists():
        return []
    return sorted(p for p in base.glob("*/artifacts.json") if p.is_file())


def load_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_index_entry(bundle: dict[str, Any], bundle_path: Path) -> RunIndexEntry:
    return RunIndexEntry(
        run_id=str(bundle.get("run_id", bundle_path.parent.name)),
        stage=str(bundle.get("stage", "unknown")),
        npc_key=str(bundle.get("npc_key", "unknown")),
        technique=str(bundle.get("technique", "unknown")),
        bundle_path=str(bundle_path),
        created_at=str(bundle.get("created_at", _iso_now())),
        metrics=bundle.get("metrics"),
        artifacts=bundle.get("artifacts"),
        metadata=bundle.get("metadata"),
    )


def refresh_run_index(
    root: Path | None = None, index_path: Path | None = None
) -> list[RunIndexEntry]:
    entries: list[RunIndexEntry] = []
    for bundle_path in iter_canonical_run_bundle_paths(root=root):
        try:
            bundle = load_bundle(bundle_path)
        except Exception:
            continue
        entries.append(build_index_entry(bundle, bundle_path))
    out = index_path or CANONICAL_INDEX_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(asdict(entry), ensure_ascii=False, default=str) + "\n")
    return entries


def latest_bundle_for_run(run_id: str, root: Path | None = None) -> Path | None:
    path = (root or CANONICAL_RUNS_ROOT) / run_id / "artifacts.json"
    return path if path.exists() else None
