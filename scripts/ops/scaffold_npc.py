#!/usr/bin/env python3
"""
scaffold_npc.py — Initialize directory structure and spec for a new NPC.

Creates:
  subjects/NPC_specs/{npc_key}.json               — validated subject spec
  subjects/reference_docs/{npc_key}_primer.md      — stub reference doc for indexing
  subjects/datasets/{npc_key}/template/            — fast/smoke dataset dir
  outputs/{npc_key}/runs/                         — training output dir
  exports/{npc_key}/                              — GGUF export dir
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from _config.paths import SNAKE_CASE_PATTERN

# Only the techniques we use — template (smoke/fast) and others
TECHNIQUES = ["template"]

DEFAULT_SPEC: dict = {
    "npc_key": "{npc_key}",
    "npc_name": "{npc_name}",
    "identity": {
        "personality": "Helpful, clear, and professional.",
        "background": "Expert in {subject}.",
        "mannerisms": "Speaks in short, clear sentences.",
    },
    "teaching": {
        "expertise": ["basics", "advanced topics"],
        "approach": "Direct and clear explanations.",
        "difficulty_levels": ["beginner"],
    },
    "concepts": [
        {
            "name": "core concepts",
            "category": "teaching",
            "difficulty": "beginner",
            "aliases": ["fundamentals"]
        }
    ],
    "dialogue": {
        "conversation_style": "Informative",
        "max_sentences": 3,
        "example_topics": [
            "Introduction to {subject}",
            "Common misconceptions about {subject}",
            "How to get started with {subject}",
        ],
    },
    "quest": {
        "scenarios": [
            {
                "name": "introduction_scenario",
                "description": "Learner asks an introductory question about {subject}",
            }
        ]
    },
    "refusal": {
        "boundaries": [
            "Will not provide harmful, illegal, or unsafe instructions",
            "Will not present unverified claims as factual",
            "Will not role-play as a real person or authority figure without disclaimers",
        ],
        "redirect_policy": "Redirects to safe educational content about the NPC's subject domain.",
    },
    # Research queries for knowledge retrieval
    "research_queries": [
        {
            "query": "Core concepts and fundamentals of {subject}",
            "mode": "fast",
        },
        {
            "query": "Key topics, examples, and real-world applications of {subject}",
            "mode": "fast",
        },
    ],
    "subject": "{subject}",
    # Path to the NPC's reference doc primer (created as a stub during scaffold)
    "reference_doc": "subjects/reference_docs/{npc_key}_primer.md",
    # 4-section system prompt format used by LLMUnity runtime
    "system_prompt": (
        "## IDENTITY\n"
        "Name: {npc_name} | Role: expert guide in {subject}\n"
        "\n"
        "## VOICE\n"
        "Clear and professional | Speak in 1-3 short sentences\n"
        "\n"
        "## KNOWLEDGE\n"
        "{subject}\n"
        "\n"
        "## RULES\n"
        "Stay in character as {npc_name} | Never mention you are an AI | "
        "Max 3 sentences | Redirect off-topic questions to {subject}"
    ),
    "dataset": {
        # Dataset distribution: 72 total examples
        "examples_per_category": {
            "identity": 8,
            "teaching": 32,
            "dialogue": 16,
            "quest": 8,
            "refusal": 8,
        }
    },
}

PRIMER_TEMPLATE = """# {npc_name} Primer — Quick Reference for {subject}

## Core Concepts
-

## Key Facts
-

## Common Misconceptions
-

## Examples & Scenarios
-

## References
-
"""


def validate_npc_key(npc_key: str) -> None:
    """Raise ValueError if npc_key is not valid snake_case."""
    if not SNAKE_CASE_PATTERN.fullmatch(npc_key):
        raise ValueError(npc_key)


def scaffold(
    npc_key: str,
    subject: str | None = None,
    name: str | None = None,
    force: bool = False,
    skip_spec: bool = False,
) -> None:
    validate_npc_key(npc_key)

    npc_name = name or npc_key.replace("_", " ").title().replace(" ", "")
    subject_text = subject or npc_key.replace("_", " ")

    created_dirs: list[str] = []
    skipped_dirs: list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []

    # ── 1. Subject spec ──────────────────────────────────────────────────────
    if not skip_spec:
        spec_path = paths.subjects_root() / "NPC_specs" / f"{npc_key}.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)

        if not spec_path.exists() or force:
            spec = copy.deepcopy(DEFAULT_SPEC)

            def _fill(t: str) -> str:
                return (
                    t.replace("{npc_key}", npc_key)
                    .replace("{npc_name}", npc_name)
                    .replace("{subject}", subject_text)
                )

            spec["npc_key"] = npc_key
            spec["npc_name"] = npc_name
            spec["subject"] = subject_text
            spec["reference_doc"] = _fill(spec["reference_doc"])
            spec["system_prompt"] = _fill(spec["system_prompt"])
            spec["identity"]["background"] = _fill(spec["identity"]["background"])
            spec["dialogue"]["example_topics"] = [
                _fill(t) for t in spec["dialogue"]["example_topics"]
            ]
            spec["quest"]["scenarios"][0]["description"] = _fill(
                spec["quest"]["scenarios"][0]["description"]
            )
            for rq in spec["research_queries"]:
                rq["query"] = _fill(rq["query"])

            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2, ensure_ascii=False)
            created_files.append(f"subjects/NPC_specs/{npc_key}.json")
        else:
            skipped_files.append(
                f"subjects/NPC_specs/{npc_key}.json (use --force to overwrite)"
            )
    else:
        skipped_files.append("subjects/NPC_specs/ (--skip-spec)")

    # ── 2. Reference doc primer stub ─────────────────────────────────────────
    primer_dir = paths.subjects_root() / "reference_docs"
    primer_dir.mkdir(parents=True, exist_ok=True)
    primer_path = primer_dir / f"{npc_key}_primer.md"
    if force or not primer_path.exists():
        content = PRIMER_TEMPLATE.format(
            npc_name=npc_name, subject=subject_text
        )
        with open(primer_path, "w", encoding="utf-8") as f:
            f.write(content.lstrip("\n"))
        created_files.append(f"subjects/reference_docs/{npc_key}_primer.md")
    else:
        skipped_files.append(
            f"subjects/reference_docs/{npc_key}_primer.md (already exists — edit to fill in content)"
        )

    # ── 3. Dataset folders ──────────────────────────────────────────────────────
    for tech in TECHNIQUES:
        tech_dir = paths.dataset_dir(npc_key) / tech
        if force or not tech_dir.exists():
            tech_dir.mkdir(parents=True, exist_ok=True)
            (tech_dir / ".gitkeep").touch()
            created_dirs.append(f"subjects/datasets/{npc_key}/{tech}/")
        else:
            skipped_dirs.append(
                f"subjects/datasets/{npc_key}/{tech}/ (already exists)"
            )

    # ── 4. Outputs dir (training) ───────────────────────────────────────────
    output_dir = paths.output_dir(npc_key)
    runs_dir = output_dir / "runs"
    if force or not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / ".gitkeep").touch()
        created_dirs.append(f"outputs/{npc_key}/")
        created_dirs.append(f"outputs/{npc_key}/runs/")
    else:
        skipped_dirs.append(f"outputs/{npc_key}/ (already exists)")

    # ── 5. Exports dir (GGUF) ──────────────────────────────────────────────
    export_dir = paths.export_dir(npc_key)
    if force or not export_dir.exists():
        export_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(f"exports/{npc_key}/")
    else:
        skipped_dirs.append(f"exports/{npc_key}/ (already exists)")

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\nNPC '{npc_key}' scaffolded successfully.\n")

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
    if skip_spec:
        print(
            "  Next steps (spec was skipped — create or edit"
            f" subjects/NPC_specs/{npc_key}.json manually):"
        )
    else:
        print("  Next steps:")
    print(f"    1. Edit subjects/reference_docs/{npc_key}_primer.md"
          f" with actual domain content")
    print(f"    2. Validate spec:  ./ucore validate-spec subjects/NPC_specs/{npc_key}.json")
    print(f"    3. Generate:       ./ucore generate subjects/NPC_specs/{npc_key}.json"
          f" --technique template")
    print(f"    4. Sanitize:       ./ucore sanitize"
          f" subjects/datasets/{npc_key}/template/train.jsonl")
    print(f"    5. Train & export: ./ucore train subjects/NPC_specs/{npc_key}.json"
          f" --technique template --preset fast-3b --export-gguf")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scaffold a new NPC (folders + spec template)"
    )
    parser.add_argument("npc_key", help="NPC key (snake_case)")
    parser.add_argument(
        "--subject", help="Subject description (default: auto-derived from npc_key)"
    )
    parser.add_argument(
        "--name", help="NPC display name (default: auto-derived from npc_key)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing spec"
    )
    parser.add_argument(
        "--skip-spec",
        action="store_true",
        help="Only create folders, skip spec file",
    )

    args = parser.parse_args()
    try:
        scaffold(args.npc_key, args.subject, args.name, args.force, args.skip_spec)
    except ValueError as exc:
        print(
            f"Error: npc_key '{exc}' must be snake_case "
            "(lowercase letters, numbers, underscores, starting with a letter).",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
