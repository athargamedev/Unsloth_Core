#!/usr/bin/env python3
"""
migrate_datasets.py — Migrate legacy flat dataset files to canonical structure.

Legacy examples:
- datasets/chemistry_instructor.jsonl
- datasets/chemistry_instructor_validation.jsonl
- datasets/chemistry_instructor_ollama.jsonl
- datasets/chemistry_instructor_ollama_validation.jsonl

Canonical target:
- datasets/{npc_key}/{technique}/train.jsonl
- datasets/{npc_key}/{technique}/validation.jsonl
"""

import argparse
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASETS = PROJECT_ROOT / "datasets"

TECHNIQUE_SUFFIX = {
    "": "notebooklm",
    "_ollama": "ollama",
    "_template": "template",
    "_openai": "openai",
    "_anthropic": "anthropic",
}


def parse_legacy_name(stem: str):
    # chemistry_instructor_validation
    is_validation = stem.endswith("_validation")
    base = stem[:-11] if is_validation else stem

    for suffix, technique in TECHNIQUE_SUFFIX.items():
        if suffix and base.endswith(suffix):
            npc_key = base[: -len(suffix)]
            return npc_key, technique, is_validation
    return base, "notebooklm", is_validation


def proposed_migrations():
    plans = []
    for f in sorted(DATASETS.glob("*.jsonl")):
        npc_key, technique, is_validation = parse_legacy_name(f.stem)
        target = DATASETS / npc_key / technique / ("validation.jsonl" if is_validation else "train.jsonl")
        plans.append((f, target))
    return plans


def main():
    parser = argparse.ArgumentParser(description="Migrate legacy flat datasets into canonical directories.")
    parser.add_argument("--apply", action="store_true", help="Apply migrations (default is dry-run)")
    parser.add_argument("--move", action="store_true", help="Move files instead of copy")
    args = parser.parse_args()

    if not DATASETS.exists():
        print(f"No datasets directory found at {DATASETS}")
        return

    plans = proposed_migrations()
    if not plans:
        print("No legacy flat *.jsonl datasets found.")
        return

    print("Planned migrations:")
    for src, dst in plans:
        print(f"- {src} -> {dst}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to execute.")
        return

    for src, dst in plans:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if args.move:
            shutil.move(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

    mode = "moved" if args.move else "copied"
    print(f"\nDone. Legacy files {mode} to canonical structure.")


if __name__ == "__main__":
    main()
