#!/usr/bin/env python3
"""Backup cleanup — move .pre_* debris to .pipeline/backups/ with retention.

Run standalone:
    python src/core/ops/backup_cleanup.py

Or via ucore:
    ucore history backup --retain 10
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def find_backup_candidates(project_root: Path) -> list[tuple[Path, str, str]]:
    """Find .pre_* files and return (src_path, npc_key, technique)."""
    candidates = []
    # Search data/datasets/ for .pre_* files
    datasets_dir = project_root / "data" / "datasets"
    if datasets_dir.exists():
        for npc_dir in sorted(datasets_dir.iterdir()):
            if not npc_dir.is_dir():
                continue
            for tech_dir in npc_dir.iterdir():
                if not tech_dir.is_dir():
                    continue
                for f in tech_dir.glob("*pre_*"):
                    if f.is_file():
                        candidates.append((f, npc_dir.name, tech_dir.name))
    # Search subjects/datasets/ too (legacy pattern)
    subjects_dir = project_root / "subjects" / "datasets"
    if subjects_dir.exists():
        for npc_dir in sorted(subjects_dir.iterdir()):
            if not npc_dir.is_dir():
                continue
            for tech_dir in npc_dir.iterdir():
                if not tech_dir.is_dir():
                    continue
                for f in tech_dir.glob("*pre_*"):
                    if f.is_file():
                        candidates.append((f, npc_dir.name, tech_dir.name))
    return candidates


def run_cleanup(project_root: Path, retain: int = 10, dry_run: bool = False) -> dict:
    """Move .pre_* files to .pipeline/backups/ and enforce retention.

    Returns summary dict with counts.
    """
    candidates = find_backup_candidates(project_root)
    backups_base = project_root / ".pipeline" / "backups"
    
    moved = 0
    errors = 0
    by_pattern: dict[str, int] = {}

    for src, npc_key, technique in candidates:
        # Derive original filename pattern (e.g., train_clean.jsonl from train_clean.jsonl.pre_*)
        orig_name = src.name
        if ".pre_" in orig_name:
            orig_name = orig_name[: orig_name.index(".pre_")]

        # Target path: .pipeline/backups/{npc_key}/{technique}/{orig_name}/{src.name}
        target_dir = backups_base / npc_key / technique / orig_name
        target = target_dir / src.name

        if dry_run:
            print(f"[DRY RUN] Would move: {src} -> {target}")
            moved += 1
            by_pattern[orig_name] = by_pattern.get(orig_name, 0) + 1
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(target))
            print(f"Moved: {src.name} -> .pipeline/backups/{npc_key}/{technique}/{orig_name}/")
            moved += 1
            by_pattern[orig_name] = by_pattern.get(orig_name, 0) + 1
        except OSError as e:
            print(f"Error moving {src.name}: {e}", file=sys.stderr)
            errors += 1

    # Enforce retention policy (keep latest N per file pattern per NPC/technique)
    pruned = 0
    if not dry_run:
        for npc_dir in sorted(backups_base.iterdir()):
            if not npc_dir.is_dir():
                continue
            for tech_dir in npc_dir.iterdir():
                if not tech_dir.is_dir():
                    continue
                for pattern_dir in tech_dir.iterdir():
                    if not pattern_dir.is_dir():
                        continue
                    backups = sorted(pattern_dir.iterdir(), key=lambda p: p.stat().st_mtime)
                    if len(backups) > retain:
                        to_remove = backups[: len(backups) - retain]
                        for old in to_remove:
                            old.unlink()
                            print(f"Pruned (retention={retain}): {old}")
                            pruned += 1

    return {
        "moved": moved,
        "errors": errors,
        "pruned": pruned,
        "by_pattern": by_pattern,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up .pre_* backup debris")
    parser.add_argument("--retain", type=int, default=10, help="Max backups to keep per pattern (default: 10)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be moved without doing it")
    args = parser.parse_args()
    
    result = run_cleanup(PROJECT_ROOT, retain=args.retain, dry_run=args.dry_run)
    
    print(f"\nSummary: {result['moved']} moved, {result['pruned']} pruned, {result['errors']} errors")
    if result["by_pattern"]:
        print("By file type:")
        for pattern, count in sorted(result["by_pattern"].items()):
            print(f"  {pattern}: {count}")


if __name__ == "__main__":
    main()
