#!/usr/bin/env python3
"""Build a golden evaluation dataset from NPC training JSONL files.

Reads all NPC training datasets (ChatML format), extracts user/assistant
exchanges, balances across categories, and writes a DeepEval-compatible
golden JSON file for NPC model evaluation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_NPC_KEYS = ("history_guide", "chef_assistant", "astronomy_guide", "fitness_coach")
DEFAULT_CATEGORIES = ("identity", "teaching", "dialogue", "quest", "refusal")
GOLDENS_OUTPUT = PROJECT_ROOT / "tests" / "evals" / ".dataset" / "npc_goldens.json"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_npc_key(key: str) -> str:
    """Validate npc_key matches ``^[a-z][a-z0-9_]*$`. Returns key on success."""
    if not re.match(r"^[a-z][a-z0-9_]*$", key):
        raise ValueError(f"Invalid npc_key: {key!r} — must match ^[a-z][a-z0-9_]*$")
    return key


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _load_spec(npc_key: str) -> dict:
    """Load the NPC spec JSON, returning empty dict on failure."""
    _validate_npc_key(npc_key)
    path = PROJECT_ROOT / "subjects" / "NPC_specs" / f"{npc_key}.json"
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_reference_doc(spec: dict) -> str:
    """Load the reference doc text from the spec's reference_doc path."""
    ref = spec.get("reference_doc", "")
    if not ref:
        return ""
    path = PROJECT_ROOT / ref
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# ---------------------------------------------------------------------------
# Dataset row iteration
# ---------------------------------------------------------------------------

def _find_dataset(npc_key: str, technique: str = "ollama") -> Path | None:
    """Locate the training JSONL for an NPC, preferring train_clean.jsonl."""
    _validate_npc_key(npc_key)
    base = PROJECT_ROOT / "subjects" / "datasets" / npc_key / technique
    clean = base / "train_clean.jsonl"
    if clean.exists():
        return clean
    raw = base / "train.jsonl"
    if raw.exists():
        return raw
    return None


def _iter_rows(path: Path) -> list[dict]:
    """Read all valid JSONL rows from *path*, skipping blank lines."""
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        print(f"[warn] Cannot read {path}: {exc}", file=sys.stderr)
        return rows

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            print(f"[warn]  {path}:{line_number} — {exc}", file=sys.stderr)
            continue
        row["_dataset_path"] = str(path)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Message extraction
# ---------------------------------------------------------------------------

def _system_prompt(messages: list[dict]) -> str:
    """Return the system message content, or empty string."""
    for msg in messages:
        if msg.get("role") == "system":
            return str(msg.get("content", ""))
    return ""


def _extract_turns(messages: list[dict]) -> list[dict]:
    """Extract user/assistant turn dicts from a ChatML message list."""
    return [
        {"role": m["role"], "content": str(m.get("content", ""))}
        for m in messages
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


def _is_multi_turn(messages: list[dict]) -> bool:
    """True when messages contain more than one user/assistant exchange."""
    return sum(1 for m in messages if m.get("role") in ("user", "assistant")) > 2


# ---------------------------------------------------------------------------
# Golden construction
# ---------------------------------------------------------------------------

def _build_multi_turn_golden(
    turns: list[dict],
    context: list[str],
    metadata: dict,
    tags: list[str],
    npc_key: str,
) -> dict:
    """Wrap multiple conversation turns into a golden dict."""
    return {
        "conversation": turns,
        "context": context,
        "metadata": {
            "npc_key": npc_key,
            "category": metadata.get("category", "unknown"),
            "concept": metadata.get("concept", ""),
        },
        "tags": tags + ["conversational"],
    }


def _row_to_goldens(row: dict, spec: dict, reference_doc: str, npc_key: str) -> list[dict]:
    """Convert one ChatML row into zero or more golden entries."""
    messages = row.get("messages", [])
    if not messages:
        return []

    metadata = row.get("metadata", {})
    category = metadata.get("category", "unknown")
    concept = metadata.get("concept", "")

    system = _system_prompt(messages)
    context_parts = [
        f"System prompt:\n{system}",
        f"Subject:\n{spec.get('subject', '')}",
    ]
    # Truncate to ~6000 chars to stay within typical LLM context budgets for the judge model
    if reference_doc:
        context_parts.append(f"Reference doc:\n{reference_doc[:6000]}")
    context = context_parts
    tags = [npc_key, category]
    turns = _extract_turns(messages)

    if not turns:
        return []

    if _is_multi_turn(messages):
        return [_build_multi_turn_golden(turns, context, metadata, tags, npc_key)]
    else:
        # Single-turn: first user turn is input, first assistant turn is output
        user_msg = None
        assistant_msg = None
        for t in turns:
            if t["role"] == "user" and user_msg is None:
                user_msg = t["content"]
            elif t["role"] == "assistant" and assistant_msg is None:
                assistant_msg = t["content"]

        if not user_msg or not assistant_msg:
            return []

        return [{
            "input": user_msg,
            "actual_output": assistant_msg,
            "context": context,
            "metadata": {
                "npc_key": npc_key,
                "category": category,
                "concept": concept,
            },
            "tags": tags,
        }]


# ---------------------------------------------------------------------------
# Category-balanced selection
# ---------------------------------------------------------------------------

def _select_balanced(
    single_turn: list[dict],
    multi_turn: list[dict],
    categories: tuple[str, ...],
    per_category: int,
) -> list[dict]:
    """Select up to *per_category* entries per category, preferring single-turn."""
    selected: list[dict] = []
    counts: dict[str, int] = Counter()

    def _pick(candidate: dict) -> bool:
        cat = candidate["metadata"]["category"]
        if cat not in categories:
            return False
        if counts[cat] >= per_category:
            return False
        counts[cat] += 1
        selected.append(candidate)
        return True

    # First pass: single-turn entries
    for golden in single_turn:
        _pick(golden)

    # Second pass: fill remaining slots with multi-turn entries
    for golden in multi_turn:
        _pick(golden)

    return selected


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def build(
    npc_keys: tuple[str, ...] = DEFAULT_NPC_KEYS,
    categories: tuple[str, ...] = DEFAULT_CATEGORIES,
    per_category: int = 6,
    output: Path = GOLDENS_OUTPUT,
    technique: str = "ollama",
) -> dict[str, Any]:
    """Read NPC datasets and write a balanced golden-evaluation file.

    Returns a summary dict with per-NPC statistics.
    """
    all_goldens: list[dict] = []
    stats: dict[str, dict[str, int]] = {}

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        probe = output.parent / ".write_test"
        probe.touch()
        probe.unlink()
    except (OSError, PermissionError) as exc:
        print(f"Error: Output path not writable: {output} — {exc}", file=sys.stderr)
        sys.exit(1)

    for npc_key in npc_keys:
        dataset_path = _find_dataset(npc_key, technique=technique)
        if dataset_path is None:
            print(f"[warn] No dataset found for NPC '{npc_key}' — skipping", file=sys.stderr)
            stats[npc_key] = {"rows": 0, "single_candidates": 0, "multi_candidates": 0, "selected": 0}
            continue

        spec = _load_spec(npc_key)
        reference_doc = _load_reference_doc(spec)
        rows = _iter_rows(dataset_path)

        single_candidates: list[dict] = []
        multi_candidates: list[dict] = []

        for row in rows:
            row_cat = row.get("metadata", {}).get("category", "unknown")
            if row_cat not in categories:
                continue

            goldens = _row_to_goldens(row, spec, reference_doc, npc_key)
            for g in goldens:
                if "conversation" in g:
                    multi_candidates.append(g)
                else:
                    single_candidates.append(g)

        selected = _select_balanced(single_candidates, multi_candidates, categories, per_category)
        all_goldens.extend(selected)

        stats[npc_key] = {
            "rows": len(rows),
            "single_candidates": len(single_candidates),
            "multi_candidates": len(multi_candidates),
            "selected": len(selected),
        }

        print(
            f"  {npc_key:20s}  {len(rows):3d} rows  →  "
            f"{len(single_candidates):3d} single  {len(multi_candidates):3d} multi  →  "
            f"{len(selected):2d} goldens"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(all_goldens, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return {"total_goldens": len(all_goldens), "per_npc": stats}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build golden evaluation dataset from NPC training files"
    )
    parser.add_argument(
        "--npc-keys",
        default=",".join(DEFAULT_NPC_KEYS),
        help=f"Comma-separated NPC keys (default: {','.join(DEFAULT_NPC_KEYS)})",
    )
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help=f"Comma-separated categories (default: {','.join(DEFAULT_CATEGORIES)})",
    )
    parser.add_argument(
        "--per-category",
        type=int,
        default=6,
        help="Target goldens per category per NPC (default: 6 → ~30/NPC)",
    )
    parser.add_argument(
        "--technique",
        default="ollama",
        help="Dataset technique subdirectory (default: ollama)",
    )
    parser.add_argument(
        "--output",
        default=str(GOLDENS_OUTPUT),
        help=f"Output JSON path (default: {GOLDENS_OUTPUT})",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    npc_keys = tuple(k.strip() for k in args.npc_keys.split(",") if k.strip())
    categories = tuple(c.strip() for c in args.categories.split(",") if c.strip())

    if not npc_keys:
        print("Error: --npc-keys is empty. Provide at least one NPC key.", file=sys.stderr)
        sys.exit(1)

    for key in npc_keys:
        try:
            _validate_npc_key(key)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    print(f"Building goldens for NPCs:   {', '.join(npc_keys)}")
    print(f"Categories:                  {', '.join(categories)}")
    print(f"Target per category per NPC: {args.per_category}")
    print(f"Output:                      {args.output}")
    print()

    result = build(npc_keys, categories, args.per_category, Path(args.output), args.technique)

    print(f"\nDone — {result['total_goldens']} total goldens written to {args.output}")
    for npc_key, s in result["per_npc"].items():
        print(f"  {npc_key}: {s['selected']} goldens from {s['rows']} rows")


if __name__ == "__main__":
    main()
