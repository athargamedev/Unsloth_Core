#!/usr/bin/env python3
"""
scaffold_npc.py — Initialize directory structure and spec for a new NPC.

Creates:
  subjects/{npc_key}.json   — validated subject spec
  datasets/{npc_key}/...    — per-technique dataset folders
  outputs/{npc_key}/        — training output dir (runs/)
  exports/{npc_key}/        — GGUF export dir
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

TECHNIQUES = ["notebooklm", "ollama", "template", "openai", "anthropic"]

DEFAULT_SPEC = {
    "npc_key": "{npc_key}",
    "npc_name": "{npc_name}",
    "identity": {
        "personality": "Helpful, clear, and professional.",
        "background": "Expert in {subject}.",
        "mannerisms": "Speaks in short, clear sentences."
    },
    "teaching": {
        "expertise": ["basics", "advanced topics"],
        "approach": "Direct and clear explanations.",
        "difficulty_levels": ["beginner"]
    },
    "dialogue": {
        "conversation_style": "Informative",
        "max_sentences": 3,
        "example_topics": [
            "Introduction to {subject}",
            "Common misconceptions about {subject}",
            "How to get started with {subject}"
        ]
    },
    "quest": {
        "scenarios": [
            {
                "name": "introduction_scenario",
                "description": "Learner asks an introductory question about {subject}"
            }
        ]
    },
    "refusal": {
        "boundaries": [
            "Will not provide harmful, illegal, or unsafe instructions",
            "Will not present unverified claims as factual",
            "Will not role-play as a real person or authority figure without disclaimers"
        ],
        "redirect_policy": "Redirects to safe educational content about the NPC's subject domain."
    },
    "research_queries": [
        {
            "query": "Fundamentals of {subject} core concepts beginner guide",
            "mode": "fast",
            "from": "web",
            "source_policy": "text-web"
        },
        {
            "query": "{subject} key topics examples and real-world applications",
            "mode": "fast",
            "from": "web",
            "source_policy": "text-web"
        }
    ],
    "subject": "{subject}",
    "system_prompt": "You are {npc_name}. Subject: {subject}. Style: clear and professional. Rules: Speak in 1-3 short sentences. Stay in character as {npc_name}. Never mention you are an AI. Max 3 sentences.",
    "dataset": {
        "examples_per_category": {
            "identity": 5,
            "teaching": 10,
            "dialogue": 10,
            "quest": 5,
            "refusal": 5
        }
    }
}


def validate_npc_key(npc_key: str) -> None:
    """Exit with error if npc_key is not valid snake_case."""
    if not SNAKE_CASE_RE.fullmatch(npc_key):
        print(
            f"Error: npc_key '{npc_key}' must be snake_case "
            "(lowercase letters, numbers, underscores, starting with a letter).",
            file=sys.stderr,
        )
        sys.exit(1)


def scaffold(npc_key: str, subject: str | None = None, name: str | None = None,
             force: bool = False, skip_spec: bool = False) -> None:
    validate_npc_key(npc_key)

    npc_name = name or npc_key.replace("_", " ").title().replace(" ", "")
    subject_text = subject or npc_key.replace("_", " ")

    created_dirs: list[str] = []
    skipped_dirs: list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []

    # ── 1. Subject spec ──────────────────────────────────────────────────────
    if not skip_spec:
        spec_path = PROJECT_ROOT / "subjects" / f"{npc_key}.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)

        if not spec_path.exists() or force:
            spec_json = json.dumps(DEFAULT_SPEC)
            spec_json = spec_json \
                .replace("{npc_key}", npc_key) \
                .replace("{npc_name}", npc_name) \
                .replace("{subject}", subject_text)
            spec = json.loads(spec_json)

            with open(spec_path, "w") as f:
                json.dump(spec, f, indent=2)
            created_files.append(f"subjects/{npc_key}.json")
        else:
            skipped_files.append(f"subjects/{npc_key}.json (use --force to overwrite)")
    else:
        skipped_files.append("subjects/ (--skip-spec)")

    # ── 2. Dataset folders ──────────────────────────────────────────────────
    for tech in TECHNIQUES:
        tech_dir = PROJECT_ROOT / "datasets" / npc_key / tech
        if not tech_dir.exists():
            tech_dir.mkdir(parents=True, exist_ok=True)
            (tech_dir / ".gitkeep").touch()
            created_dirs.append(f"datasets/{npc_key}/{tech}/")
        else:
            skipped_dirs.append(f"datasets/{npc_key}/{tech}/ (already exists)")

    # ── 3. Outputs dir (training) ───────────────────────────────────────────
    output_dir = PROJECT_ROOT / "outputs" / npc_key
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "runs").mkdir(parents=True, exist_ok=True)
        created_dirs.append(f"outputs/{npc_key}/")
        created_dirs.append(f"outputs/{npc_key}/runs/")
    else:
        skipped_dirs.append(f"outputs/{npc_key}/ (already exists)")

    # ── 4. Exports dir (GGUF) ──────────────────────────────────────────────
    export_dir = PROJECT_ROOT / "exports" / npc_key
    if not export_dir.exists():
        export_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(f"exports/{npc_key}/")
    else:
        skipped_dirs.append(f"exports/{npc_key}/ (already exists)")

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\nNPC '{npc_key}' scaffolded successfully.")
    print()

    if created_files:
        print("  Created files:")
        for f in created_files:
            print(f"    {f}")
    if skipped_files:
        print("  Skipped files:")
        for f in skipped_files:
            print(f"    {f}")
    if created_dirs:
        print("  Created directories:")
        for d in created_dirs:
            print(f"    {d}")
    if skipped_dirs:
        print("  Skipped directories:")
        for d in skipped_dirs:
            print(f"    {d}")

    print()
    print("  Next steps:")
    print(f"    ./ucore validate-spec subjects/{npc_key}.json")
    print(f"    ./ucore generate subjects/{npc_key}.json --technique template")
    print(f"    ./ucore sanitize datasets/{npc_key}/template/train.jsonl")
    print(f"    ./ucore validate-config --spec subjects/{npc_key}.json --preset smoke --data datasets/{npc_key}/template/train_clean.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new NPC (folders + spec template)")
    parser.add_argument("npc_key", help="NPC key (snake_case)")
    parser.add_argument("--subject", help="Subject description (default: auto-derived from npc_key)")
    parser.add_argument("--name", help="NPC display name (default: auto-derived from npc_key)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing spec")
    parser.add_argument("--skip-spec", action="store_true", help="Only create folders, skip spec file")

    args = parser.parse_args()
    scaffold(args.npc_key, args.subject, args.name, args.force, args.skip_spec)


if __name__ == "__main__":
    main()
