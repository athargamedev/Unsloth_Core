#!/usr/bin/env python3
from __future__ import annotations

"""Dry-run or apply cleanup of legacy dataset/eval artifacts."""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.config.paths import PROJECT_ROOT
from src.core.ops.legacy_data_cleanup import iter_legacy_dataset_artifacts, summarize_targets


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean legacy dataset/eval artifacts")
    parser.add_argument("--apply", action="store_true", help="Actually remove matched artifacts")
    parser.add_argument(
        "--archive-dir",
        default="var/archive/legacy-data",
        help="Archive directory used when --apply is set",
    )
    args = parser.parse_args()

    targets = list(iter_legacy_dataset_artifacts())
    summary = summarize_targets(targets)
    print(f"targets={len(targets)}")
    for reason, count in sorted(summary.items()):
        print(f"{reason}: {count}")

    for target in targets[:50]:
        print(f"- {target.path} :: {target.reason}")

    if not args.apply:
        return 0

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        if not target.path.exists():
            continue
        try:
            rel = target.path.relative_to(PROJECT_ROOT)
        except Exception:
            rel = Path(target.path.name)
        dest = archive_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target.path), str(dest))
    print(f"archived={len(targets)} to {archive_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
