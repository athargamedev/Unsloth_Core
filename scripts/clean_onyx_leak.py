#!/usr/bin/env python3
"""
Clean Onyx metadata JSON leaks from NPC training datasets.

Onyx generation occasionally injects document metadata like:
  ine and exercise science" }, "subject": "Fitness...", "reference_doc": "subj...
into the assistant response text. This script detects and removes those fragments.

Usage:
  python3 scripts/clean_onyx_leak.py subjects/datasets/fitness_coach/onyx/train.jsonl
  python3 scripts/clean_onyx_leak.py subjects/datasets/fitness_coach/onyx/train_clean.jsonl
  python3 scripts/clean_onyx_leak.py subjects/datasets/fitness_coach/onyx/validation.jsonl
"""

import json
import re
import sys

# Pattern: Onyx metadata JSON leak fragment
# Matches from the truncated word fragment through the "subject" and "reference_doc" keys
# Examples:
#   ine and exercise science" }, "subject": "Fitness...", "reference_doc": "subj It's...
ONYX_LEAK_PATTERN = re.compile(
    r'\s*ine and exercise science"\s*\}\s*,\s*"subject":\s*"[^"]*",\s*"reference_doc":\s*"subj[^"]*"\s*'
)

# Sometimes the reference_doc value isn't closed
ONYX_LEAK_PATTERN_OPEN = re.compile(
    r'\s*ine and exercise science"\s*\}\s*,\s*"subject":\s*"[^"]*",\s*"reference_doc":\s*"subj[^"]*'
)


def clean_onyx_fragment(text: str) -> str:
    """Remove Onyx metadata JSON fragments from text."""
    original = text
    text = ONYX_LEAK_PATTERN.sub(' ', text)
    text = ONYX_LEAK_PATTERN_OPEN.sub(' ', text)
    # Clean up double spaces and trim
    text = re.sub(r'  +', ' ', text)
    text = text.strip()
    return text


def clean_file(path: str, dry_run: bool = True) -> dict:
    """Clean a JSONL dataset file. Returns stats."""
    with open(path) as f:
        lines = f.readlines()

    total = len(lines)
    cleaned = 0
    new_lines = []

    for line in lines:
        orig = json.loads(line)
        mod = json.loads(line)  # deep copy via re-parse
        changed = False
        for msg in mod['messages']:
            if msg['role'] == 'assistant':
                new_content = clean_onyx_fragment(msg['content'])
                if new_content != msg['content']:
                    msg['content'] = new_content
                    changed = True
        if changed:
            cleaned += 1
        new_lines.append(mod)

    if not dry_run:
        with open(path, 'w') as f:
            for ex in new_lines:
                f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    return {
        'path': path,
        'total': total,
        'cleaned': cleaned,
        'dry_run': dry_run,
    }


if __name__ == '__main__':
    dry_run = '--apply' not in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith('--')]

    if not paths:
        print("Usage: python3 scripts/clean_onyx_leak.py <path> [--apply]")
        print("\nWithout --apply: dry-run (show stats only)")
        print("With --apply: modify files in place")
        sys.exit(1)

    for path in paths:
        stats = clean_file(path, dry_run=dry_run)
        action = "WOULD clean" if stats['dry_run'] else "CLEANED"
        print(f"{action} {stats['path']}: {stats['cleaned']}/{stats['total']} examples affected")

        # Show examples if dry run
        if dry_run and stats['cleaned'] > 0:
            with open(path) as f:
                shown = 0
                for line in f:
                    if shown >= 3:
                        break
                    ex = json.loads(line)
                    for msg in ex['messages']:
                        if msg['role'] == 'assistant' and ('"subject"' in msg['content'] or 'ine and exercise science' in msg['content']):
                            new_content = clean_onyx_fragment(msg['content'])
                            before_text = msg['content'][:100]
                            after_text = new_content[:100]
                            if before_text != after_text:
                                print(f"  BEFORE: {before_text}...")
                                print(f"  AFTER:  {after_text}...")
                                print()
                                shown += 1
                                break
