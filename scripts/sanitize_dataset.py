#!/usr/bin/env python3
"""
sanitize_dataset.py — Clean and validate training datasets.

Usage:
    python scripts/sanitize_dataset.py datasets/my_npc/notebooklm/train.jsonl --output datasets/my_npc/notebooklm/train_clean.jsonl
"""

import argparse
import json
import os
import re
from pathlib import Path

from _config import paths

# Common AI artifacts to filter out
AI_ARTIFACT_PATTERNS = [
    r"as an AI",
    r"language model",
    r"I don't have feelings",
    r"I am not a person",
    r"my programming",
    r"openai",
    r"google",
    r"meta",
    r"llama",
    r"based on my knowledge cutoff",
    r"I am a large language model",
    r"I do not have a physical body",
    r"I cannot feel",
    r"I don't have a personal identity",
]

def contains_ai_artifact(text):
    """Check if text contains common AI artifacts."""
    for pattern in AI_ARTIFACT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, pattern
    return False, None

def sanitize_example(example, min_length=10, max_sentences=5):
    """Sanitize a single ChatML example."""
    messages = example.get("messages", [])
    if not messages:
        return None, "No messages"

    # 1. Structure check
    if not all(isinstance(m, dict) and "role" in m and "content" in m for m in messages):
        return None, "Invalid message structure"

    # 2. Role sequence check (system? -> user -> assistant -> user -> assistant ...)
    # Simple check: at least one user and one assistant message
    roles = [m["role"] for m in messages]
    if "user" not in roles or "assistant" not in roles:
        return None, "Missing user or assistant role"

    # 3. Content sanitization
    for m in messages:
        content = m.get("content", "")
        
        # AI artifact check
        has_artifact, pattern = contains_ai_artifact(content)
        if has_artifact:
            return None, f"Contains AI artifact: '{pattern}'"
            
        # Length check for assistant
        if m["role"] == "assistant":
            if len(content) < min_length:
                return None, f"Assistant response too short ({len(content)} chars)"
            
            sentences = [s.strip() for s in re.split(r'[.!?]+', content) if s.strip()]
            if len(sentences) > max_sentences:
                # Truncate instead of discarding? Let's be strict for now.
                return None, f"Assistant response too long ({len(sentences)} sentences)"

    return example, None

def main():
    parser = argparse.ArgumentParser(description="Sanitize training dataset")
    parser.add_argument("input", help="Input JSONL path")
    parser.add_argument("--output", "-o", help="Output JSONL path (defaults to input_clean.jsonl)")
    parser.add_argument("--min-length", type=int, default=10, help="Min chars for assistant response")
    parser.add_argument("--max-sentences", type=int, default=5, help="Max sentences for assistant response")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print discarded examples")
    parser.add_argument("--strict-canonical", action="store_true",
                        help="Fail unless input path is canonical datasets/{npc_key}/{technique}/train.jsonl")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} not found")
        return

    if args.strict_canonical and not paths.is_canonical_train_path(input_path):
        print("Error: Non-canonical dataset path.")
        print("Expected: datasets/{npc_key}/{technique}/train.jsonl")
        print(f"Got:      {input_path}")
        return

    output_path = Path(args.output) if args.output else input_path.parent / f"{input_path.stem}_clean.jsonl"
    
    print(f"Sanitizing: {input_path}")
    print(f"Output:     {output_path}")
    
    total = 0
    kept = 0
    discarded = 0
    reasons = {}
    
    with open(input_path, "r") as fin, open(output_path, "w") as fout:
        for line in fin:
            if not line.strip():
                continue
            total += 1
            try:
                example = json.loads(line)
                clean_ex, reason = sanitize_example(example, min_length=args.min_length, max_sentences=args.max_sentences)
                
                if clean_ex:
                    fout.write(json.dumps(clean_ex) + "\n")
                    kept += 1
                else:
                    discarded += 1
                    reasons[reason] = reasons.get(reason, 0) + 1
                    if args.verbose:
                        print(f"  [discard] {reason}")
            except Exception as e:
                discarded += 1
                reasons[str(e)] = reasons.get(str(e), 0) + 1
                
    print(f"\nStats:")
    print(f"  Total:     {total}")
    print(f"  Kept:      {kept} ({kept/total*100:.1f}%)")
    print(f"  Discarded: {discarded} ({discarded/total*100:.1f}%)")
    
    if reasons:
        print("\nReasons for discard:")
        for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count}")

if __name__ == "__main__":
    main()
