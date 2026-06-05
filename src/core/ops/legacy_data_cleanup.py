from __future__ import annotations

"""Shared helpers for auditing and cleaning legacy dataset/eval artifacts.

Policy:
- Prefer canonical data/datasets/{npc}/{technique}/ artifacts.
- Treat subjects/datasets/ as migration-only legacy storage.
- Archive or delete only clearly stale clutter (backups, pre-repair snapshots,
  versioned manifests, duplicate history snapshots) unless explicitly retained.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.config.paths import PROJECT_ROOT, dataset_root

LEGACY_DIRS = (
    PROJECT_ROOT / "subjects" / "datasets",
    PROJECT_ROOT / "artifacts" / "eval" / "deepeval_runs",
    PROJECT_ROOT / ".deepeval",
)

STALE_PATTERNS = (
    re.compile(r"\.bak$"),
    re.compile(r"\.pre_refusal_repair_\d{8}_\d{6}\.jsonl?$"),
    re.compile(r"^quality_(summary|report|failures)_(fast|identity|\d+).json$"),
    re.compile(r"^train_manifest\.pre_refusal_repair_\d{8}_\d{6}\.json$"),
)


@dataclass(frozen=True)
class CleanupTarget:
    path: Path
    reason: str


def iter_legacy_dataset_artifacts(root: Path | None = None) -> Iterable[CleanupTarget]:
    root = root or PROJECT_ROOT
    dataset_root().resolve()

    # Legacy dataset root mirror.
    subjects_root = root / "subjects" / "datasets"
    if subjects_root.exists():
        for path in subjects_root.rglob("*"):
            if path.is_file():
                yield CleanupTarget(path=path, reason="legacy subjects/datasets mirror")

    # Clearly stale clutter inside canonical data/datasets tree.
    data_root = root / "data" / "datasets"
    if data_root.exists():
        for path in data_root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if any(p.search(name) for p in STALE_PATTERNS):
                yield CleanupTarget(path=path, reason="stale backup/snapshot artifact")
            elif path.parent.name == "history" and name.startswith(
                ("quality_", "confident_insights")
            ):
                # Retain only the latest canonical files in history when explicitly needed.
                yield CleanupTarget(path=path, reason="historical quality snapshot")

    # Transient local caches should never be canonical history.
    for cache_root in (root / ".deepeval", root / "artifacts" / "eval" / "deepeval_runs"):
        if cache_root.exists():
            for path in cache_root.rglob("*"):
                if path.is_file():
                    yield CleanupTarget(path=path, reason="transient deepeval cache/run artifact")


def summarize_targets(targets: Iterable[CleanupTarget]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for target in targets:
        counts[target.reason] = counts.get(target.reason, 0) + 1
    return counts
