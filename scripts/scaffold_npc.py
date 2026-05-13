#!/usr/bin/env python3
"""
scaffold_npc.py — Initialize directory structure and spec for a new NPC.
"""

import argparse
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

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
        "example_topics": ["Introduction to {subject}"]
    },
    "research_queries": [
        {
            "query": "Fundamentals of {subject}",
            "mode": "fast",
            "from": "web",
            "source_policy": "text-web"
        }
    ],
    "subject": "{subject}",
    "system_prompt": "You are {npc_name}. Subject: {subject}. Style: clear and professional. Rules: Speak in 1-3 short sentences.",
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

def scaffold(npc_key, subject=None, name=None, force=False):
    npc_name = name or npc_key.replace("_", " ").title().replace(" ", "")
    subject_text = subject or npc_key.replace("_", " ")
    
    # 1. Create subject spec
    spec_path = PROJECT_ROOT / "subjects" / f"{npc_key}.json"
    if not spec_path.exists() or force:
        print(f"Creating subject spec: {spec_path.relative_to(PROJECT_ROOT)}")
        spec = json.loads(json.dumps(DEFAULT_SPEC).replace("{npc_key}", npc_key).replace("{npc_name}", npc_name).replace("{subject}", subject_text))
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        with open(spec_path, "w") as f:
            json.dump(spec, f, indent=2)
    else:
        print(f"Subject spec already exists: {spec_path.relative_to(PROJECT_ROOT)}")

    # 2. Create dataset folders
    for tech in TECHNIQUES:
        tech_dir = PROJECT_ROOT / "datasets" / npc_key / tech
        if not tech_dir.exists():
            print(f"Creating dataset folder: {tech_dir.relative_to(PROJECT_ROOT)}")
            tech_dir.mkdir(parents=True, exist_ok=True)
            # Create a placeholder train.jsonl if it doesn't exist
            # (optional, but helps UI if it expects the file to exist)
            # placeholder = tech_dir / "train.jsonl"
            # if not placeholder.exists():
            #    placeholder.touch()

    print(f"\nNPC '{npc_key}' scaffolded successfully.")

def main():
    parser = argparse.ArgumentParser(description="Scaffold a new NPC project structure")
    parser.add_argument("npc_key", help="NPC key (snake_case)")
    parser.add_argument("--subject", help="Subject description")
    parser.add_argument("--name", help="NPC display name")
    parser.add_argument("--force", action="store_true", help="Overwrite existing spec")
    
    args = parser.parse_args()
    scaffold(args.npc_key, args.subject, args.name, args.force)

if __name__ == "__main__":
    main()
