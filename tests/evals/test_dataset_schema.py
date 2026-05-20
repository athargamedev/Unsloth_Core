"""Structured validation suite for NPC training datasets.

Validates ChatML JSONL schema compliance directly — no DeepEval, no LLM
judges, no external dependencies beyond pytest. Runs in under 10 seconds.

Environment variables:
  DEEPEVAL_DATASET_NPC_KEYS               — Comma-separated NPC keys (default: all 4)
  DEEPEVAL_DATASET_CATEGORIES             — Comma-separated valid categories
  DEEPEVAL_DATASET_TECHNIQUE              — Generation technique subdirectory
  DEEPEVAL_DATASET_CATEGORY_MINIMUMS      — Category minima as key=value pairs (default: hardcoded)
"""

from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_NPC_KEYS = ("history_guide", "chef_assistant", "astronomy_guide", "fitness_coach")
DEFAULT_CATEGORIES = ("identity", "teaching", "dialogue", "quest", "refusal")
DEFAULT_TECHNIQUE = "ollama"

_CATEGORY_MINIMUMS_DEFAULT: dict[str, int] = {
    "identity": 12,
    "teaching": 56,
    "dialogue": 32,
    "quest": 16,
    "refusal": 16,
}

NPC_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
HTML_TAG_PATTERN = re.compile(r"<[^>]*>", re.IGNORECASE)
VALID_ROLES = frozenset({"system", "user", "assistant"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a comma-separated env var into a tuple of non-empty strings."""
    value = os.getenv(name)
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_category_minimums() -> dict[str, int]:
    """Parse ``DEEPEVAL_DATASET_CATEGORY_MINIMUMS`` or return defaults.

    Expected format: ``"identity=12,teaching=56,dialogue=32,quest=16,refusal=16"``
    """
    raw = os.getenv("DEEPEVAL_DATASET_CATEGORY_MINIMUMS")
    if not raw:
        return dict(_CATEGORY_MINIMUMS_DEFAULT)

    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not parts:
        raise ValueError(
            "DEEPEVAL_DATASET_CATEGORY_MINIMUMS is set but contains no "
            "parseable key=value pairs"
        )

    valid = set(DEFAULT_CATEGORIES)
    result: dict[str, int] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError(
                f"DEEPEVAL_DATASET_CATEGORY_MINIMUMS: invalid entry "
                f"{part!r} — expected key=value"
            )
        key, val_str = part.split("=", 1)
        key = key.strip()
        val_str = val_str.strip()

        if key not in valid:
            raise ValueError(
                f"DEEPEVAL_DATASET_CATEGORY_MINIMUMS: unknown category "
                f"{key!r} — must be one of {sorted(valid)}"
            )

        try:
            val = int(val_str)
        except ValueError:
            raise ValueError(
                f"DEEPEVAL_DATASET_CATEGORY_MINIMUMS: "
                f"category {key!r} has non-integer value {val_str!r}"
            )

        if val <= 0:
            raise ValueError(
                f"DEEPEVAL_DATASET_CATEGORY_MINIMUMS: "
                f"category {key!r} must be a positive integer, got {val}"
            )

        if key in result:
            raise ValueError(
                f"DEEPEVAL_DATASET_CATEGORY_MINIMUMS: "
                f"duplicate key {key!r}"
            )

        result[key] = val

    return result


CATEGORY_MINIMUMS: dict[str, int] = _parse_category_minimums()
CATEGORIES: tuple[str, ...] = _csv_env("DEEPEVAL_DATASET_CATEGORIES", DEFAULT_CATEGORIES)


def _resolve_dataset_path(npc_key: str, technique: str) -> Path | None:
    """Resolve dataset path, preferring clean over raw, or None if missing."""
    base = PROJECT_ROOT / "subjects" / "datasets" / npc_key / technique
    clean = base / "train_clean.jsonl"
    if clean.is_file():
        return clean
    fallback = base / "train.jsonl"
    if fallback.is_file():
        return fallback
    return None


def _load_rows() -> list[dict]:
    """Load and parse all dataset rows across every requested NPC.

    Returns a list of parsed row dicts — each guaranteed to carry the keys
    ``npc_key``, ``category``, ``concept``, ``difficulty``, ``messages``,
    ``metadata``, ``_line_number``, and ``_source_path``.
    """
    npc_keys = _csv_env("DEEPEVAL_DATASET_NPC_KEYS", DEFAULT_NPC_KEYS)
    technique = os.getenv("DEEPEVAL_DATASET_TECHNIQUE", DEFAULT_TECHNIQUE)

    rows: list[dict] = []

    for npc_key in npc_keys:
        path = _resolve_dataset_path(npc_key, technique)
        if path is None:
            warnings.warn(
                f"No dataset found for {npc_key}/{technique} — skipping",
                stacklevel=2,
            )
            continue

        with path.open(encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    warnings.warn(
                        f"Empty line {line_number} in {path.name} — skipping",
                        stacklevel=2,
                    )
                    continue

                row = json.loads(line)
                meta = row.get("metadata") or {}
                rows.append({
                    "npc_key": npc_key,
                    "category": meta.get("category", ""),
                    "concept": meta.get("concept", ""),
                    "difficulty": meta.get("difficulty", ""),
                    "messages": row.get("messages", []),
                    "metadata": meta,
                    "_line_number": line_number,
                    "_source_path": str(path.relative_to(PROJECT_ROOT)),
                })

    if not rows:
        pytest.skip(
            "No dataset rows loaded — check DEEPEVAL_DATASET_NPC_KEYS and "
            "DEEPEVAL_DATASET_TECHNIQUE",
        )

    return rows


def _build_rows_by_npc(rows: list[dict]) -> dict[str, list[dict]]:
    """Group parsed rows by ``npc_key``."""
    by_npc: dict[str, list[dict]] = {}
    for row in rows:
        by_npc.setdefault(row["npc_key"], []).append(row)
    return by_npc


def _first_user_message(messages: list[dict]) -> str:
    """Return the content of the first user message, or empty string."""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content if isinstance(content, str) else ""
    return ""


# ---------------------------------------------------------------------------
# Module-level fixture data (parsed once)
# ---------------------------------------------------------------------------

ROWS = _load_rows()
ROWS_BY_NPC = _build_rows_by_npc(ROWS)
NPC_KEYS = tuple(sorted(ROWS_BY_NPC.keys()))


def _row_id(row: dict) -> str:
    """Human-readable test ID for a single row."""
    return f"{row['npc_key']}:{row['category']}:L{row['_line_number']}"


# ===================================================================
# Tests
# ===================================================================

# ---- test_chatml_format -------------------------------------------------


@pytest.mark.parametrize("row", ROWS, ids=_row_id)
def test_chatml_format(row: dict) -> None:
    """Messages must follow ChatML: system first, then alternating user/assistant."""
    messages = row["messages"]

    # Early exit: messages must be a non-empty list
    assert isinstance(messages, list), f"messages must be a list, got {type(messages).__name__}"
    assert len(messages) > 0, "messages list must not be empty"

    # First message must be system
    first_role = messages[0].get("role", "")
    assert first_role == "system", (
        f"first message must have role='system', got '{first_role}'"
    )

    # Subsequent messages must alternate user/assistant
    for i, msg in enumerate(messages[1:], start=1):
        role = msg.get("role", "")
        expected = "user" if i % 2 == 1 else "assistant"
        assert role == expected, (
            f"message at position {i} must have role='{expected}', got '{role}'"
        )

        content = msg.get("content")
        assert content is not None, f"message at position {i} has null content"
        assert isinstance(content, str), (
            f"message at position {i} content must be a string, "
            f"got {type(content).__name__}"
        )

    # Validate system content too
    system_content = messages[0].get("content")
    assert system_content is not None, "system message has null content"
    assert isinstance(system_content, str), (
        f"system message content must be a string, got {type(system_content).__name__}"
    )

    # Every role must be in the valid set
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        assert role in VALID_ROLES, (
            f"message at position {i} has invalid role '{role}' — "
            f"must be one of {sorted(VALID_ROLES)}"
        )


# ---- test_metadata_required_fields ---------------------------------------


@pytest.mark.parametrize("row", ROWS, ids=_row_id)
def test_metadata_required_fields(row: dict) -> None:
    """Metadata must be a dict with all required keys as non-empty strings."""
    meta = row["metadata"]

    # Early exit: metadata must be a dict
    assert isinstance(meta, dict), (
        f"metadata must be a dict, got {type(meta).__name__}"
    )

    required_keys = ("npc_key", "category", "concept", "difficulty")
    for key in required_keys:
        assert key in meta, f"metadata missing required key '{key}'"
        value = meta[key]
        assert isinstance(value, str), (
            f"metadata['{key}'] must be a string, got {type(value).__name__}"
        )
        assert value.strip(), f"metadata['{key}'] must be a non-empty string"

    # npc_key must match the pattern
    npc_key = meta["npc_key"]
    assert NPC_KEY_PATTERN.match(npc_key), (
        f"metadata['npc_key']='{npc_key}' must match ^[a-z][a-z0-9_]*$"
    )


# ---- test_category_values ------------------------------------------------


@pytest.mark.parametrize("row", ROWS, ids=_row_id)
def test_category_values(row: dict) -> None:
    """Category must be one of the valid values."""
    category = row["category"]
    assert category in CATEGORIES, (
        f"category='{category}' must be one of {sorted(CATEGORIES)}"
    )


# ---- test_category_balance -----------------------------------------------


@pytest.mark.parametrize("npc_key", NPC_KEYS, ids=NPC_KEYS)
def test_category_balance(npc_key: str) -> None:
    """Each NPC must have at least the minimum rows per category."""
    rows = ROWS_BY_NPC[npc_key]
    counts: dict[str, int] = {}
    for row in rows:
        cat = row["category"]
        counts[cat] = counts.get(cat, 0) + 1

    failures: list[str] = []
    for cat, minimum in CATEGORY_MINIMUMS.items():
        actual = counts.get(cat, 0)
        if actual < minimum:
            failures.append(
                f"{cat}: got {actual}, minimum {minimum}"
            )

    assert not failures, (
        f"{npc_key}: {len(failures)} category(ies) below minimum:\n"
        + "\n".join(f"  - {f}" for f in failures)
    )


# ---- test_field_types ----------------------------------------------------


@pytest.mark.parametrize("row", ROWS, ids=_row_id)
def test_field_types(row: dict) -> None:
    """Verify the expected Python types for every metadata field and messages."""
    meta = row["metadata"]

    # Scalar types
    assert isinstance(meta.get("category"), str), "metadata.category must be a string"
    assert isinstance(meta.get("concept"), str), "metadata.concept must be a string"
    assert isinstance(meta.get("difficulty"), str), "metadata.difficulty must be a string"
    assert isinstance(meta.get("npc_key"), str), "metadata.npc_key must be a string"

    # Messages
    messages = row["messages"]
    assert isinstance(messages, list), "messages must be a list"
    for i, msg in enumerate(messages):
        assert isinstance(msg, dict), (
            f"message at position {i} must be a dict, got {type(msg).__name__}"
        )
        assert isinstance(msg.get("role"), str), (
            f"message at position {i} 'role' must be a string"
        )
        assert isinstance(msg.get("content"), str), (
            f"message at position {i} 'content' must be a string"
        )


# ---- test_no_empty_messages ----------------------------------------------


@pytest.mark.parametrize("row", ROWS, ids=_row_id)
def test_no_empty_messages(row: dict) -> None:
    """No message content may be empty, whitespace-only, contain HTML, or null bytes."""
    messages = row["messages"]

    for i, msg in enumerate(messages):
        content = msg.get("content", "")

        # Empty or whitespace-only
        assert content.strip(), (
            f"message at position {i} content is empty or whitespace-only"
        )

        # Null byte
        assert "\0" not in content, (
            f"message at position {i} contains null byte character"
        )

        # HTML tags
        assert not HTML_TAG_PATTERN.search(content), (
            f"message at position {i} contains HTML tags: "
            f"{HTML_TAG_PATTERN.findall(content)[:3]}"
        )


# ---- test_unique_rows ----------------------------------------------------


@pytest.mark.parametrize("npc_key", NPC_KEYS, ids=NPC_KEYS)
def test_unique_rows(npc_key: str) -> None:
    """No two rows share the same (category, concept, user_message) triple."""
    rows = ROWS_BY_NPC[npc_key]
    seen: set[tuple[str, str, str]] = set()
    duplicates: list[str] = []

    for row in rows:
        key = (
            row["category"],
            row["concept"],
            _first_user_message(row["messages"]),
        )
        if key in seen:
            duplicates.append(
                f"  category='{key[0]}', concept='{key[1]}'"
            )
        seen.add(key)

    assert not duplicates, (
        f"{npc_key}: {len(duplicates)} duplicate(s) found "
        f"(same category + concept + user message):\n"
        + "\n".join(duplicates)
    )
