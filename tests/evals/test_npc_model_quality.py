"""DeepEval suite for evaluating NPC model response quality.

Consumes a golden dataset built by ``scripts/evaluation/build_npc_goldens.py``
and runs the same metric families used for dataset quality gating plus
conversational metrics when multi-turn goldens are available.

Environment variables:
  DEEPEVAL_OLLAMA_MODEL           — Judge model name (default: qwen3)
  DEEPEVAL_OLLAMA_BASE_URL        — Ollama server URL
  DEEPEVAL_OLLAMA_TEMPERATURE     — Judge temperature
  DEEPEVAL_GOLDEN_NPC_KEYS        — Comma-separated NPC keys (default: all 4)
  DEEPEVAL_GOLDEN_CATEGORIES      — Comma-separated categories (default: all 5)
  DEEPEVAL_GOLDEN_PER_CATEGORY    — Goldens per category per NPC (default: 3)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn

# Set default judge model *before* importing metrics so the module-level
# JUDGE_MODEL picks it up when this is the first metrics import.
os.environ.setdefault("DEEPEVAL_OLLAMA_MODEL", "qwen3")
os.environ.setdefault("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDENS_PATH = PROJECT_ROOT / "tests" / "evals" / ".dataset" / "npc_goldens.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import (
    CONVERSATIONAL_METRICS,
    DATASET_QUALITY_METRICS,
    RAG_QUALITY_METRICS,
    SAFETY_METRICS,
)

# ---------------------------------------------------------------------------
# Clone metrics with sync mode — async metrics don't serialize scores
# properly in this test's single-threaded context
# ---------------------------------------------------------------------------

def _make_sync(metrics_list: list) -> list:
    for m in metrics_list:
        m.async_mode = False
    return metrics_list

DATASET_QUALITY_METRICS = _make_sync(DATASET_QUALITY_METRICS)
RAG_QUALITY_METRICS = _make_sync(RAG_QUALITY_METRICS)
CONVERSATIONAL_METRICS = _make_sync(CONVERSATIONAL_METRICS)
SAFETY_METRICS = _make_sync(SAFETY_METRICS)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

ALL_NPC_KEYS = ("history_guide", "chef_assistant", "astronomy_guide", "fitness_coach")
ALL_CATEGORIES = ("identity", "teaching", "dialogue", "quest", "refusal")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a comma-separated env var into a tuple of non-empty strings."""
    value = os.getenv(name)
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _load_goldens() -> list[dict]:
    """Load the golden dataset from the well-known path."""
    if not GOLDENS_PATH.exists():
        raise FileNotFoundError(
            f"Golden dataset not found at {GOLDENS_PATH}.\n"
            f"Run: python scripts/evaluation/build_npc_goldens.py"
        )
    with GOLDENS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _is_single_turn(golden: dict) -> bool:
    """True if this golden is a single-turn (input/output) entry."""
    return "conversation" not in golden


def _matches_filter(golden: dict, npc_keys: tuple[str, ...], categories: tuple[str, ...]) -> bool:
    """Check whether a golden matches the NPC-key and category filters."""
    meta = golden.get("metadata", {})
    return meta.get("npc_key") in npc_keys and meta.get("category") in categories


def _to_llm_test_case(golden: dict) -> LLMTestCase:
    """Convert a single-turn golden dict into an LLMTestCase."""
    meta = golden.get("metadata", {})
    return LLMTestCase(
        name=f"{meta['npc_key']}:{meta['category']}:{meta.get('concept', 'unknown')}",
        input=golden.get("input", ""),
        actual_output=golden.get("actual_output", ""),
        expected_output=golden.get("actual_output", ""),
        context=golden.get("context", []),
        retrieval_context=list(golden.get("context", [])),
        metadata=meta,
        tags=golden.get("tags", []),
    )


def _to_conversational_test_case(golden: dict) -> ConversationalTestCase:
    """Convert a multi-turn golden dict into a ConversationalTestCase."""
    meta = golden.get("metadata", {})
    turns = [
        Turn(role=t["role"], content=t["content"])
        for t in golden.get("conversation", [])
    ]
    return ConversationalTestCase(
        name=f"{meta['npc_key']}:conv:{meta['category']}:{meta.get('concept', 'unknown')}",
        turns=turns,
        metadata=meta,
        tags=golden.get("tags", []),
    )


def _build_cases() -> tuple[list[LLMTestCase], list[ConversationalTestCase]]:
    """Load and filter goldens, returning single-turn and multi-turn lists."""
    npc_keys = _csv_env("DEEPEVAL_GOLDEN_NPC_KEYS", ALL_NPC_KEYS)
    categories = _csv_env("DEEPEVAL_GOLDEN_CATEGORIES", ALL_CATEGORIES)
    per_category = int(os.getenv("DEEPEVAL_GOLDEN_PER_CATEGORY", "3"))

    goldens = _load_goldens()

    # Filter by NPC key and category
    matching = [g for g in goldens if _matches_filter(g, npc_keys, categories)]

    # Apply per-category cap
    counts: dict[str, int] = {}
    capped: list[dict] = []
    for golden in matching:
        cat = golden.get("metadata", {}).get("category", "unknown")
        if counts.get(cat, 0) >= per_category:
            continue
        counts[cat] = counts.get(cat, 0) + 1
        capped.append(golden)

    # Separate into single-turn and multi-turn
    single = [_to_llm_test_case(g) for g in capped if _is_single_turn(g)]
    multi = [_to_conversational_test_case(g) for g in capped if not _is_single_turn(g)]

    if not single and not multi:
        pytest.skip("No golden test cases matched the current filter criteria")

    return single, multi


# ---------------------------------------------------------------------------
# Module-level test case construction (runs once at import time)
# ---------------------------------------------------------------------------

try:
    SINGLE_TURN_CASES, MULTI_TURN_CASES = _build_cases()
except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
    pytest.skip(f"Cannot load golden dataset: {exc}", allow_module_level=True)
    SINGLE_TURN_CASES, MULTI_TURN_CASES = [], []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("test_case", SINGLE_TURN_CASES, ids=lambda c: c.name)
def test_npc_single_turn_response(test_case: LLMTestCase) -> None:
    """Evaluate single-turn NPC responses on quality, RAG faithfulness, and safety."""
    assert_test(
        test_case=test_case,
        metrics=DATASET_QUALITY_METRICS + RAG_QUALITY_METRICS + SAFETY_METRICS,
    )


@pytest.mark.parametrize("test_case", MULTI_TURN_CASES, ids=lambda c: c.name)
def test_npc_conversational_response(test_case: ConversationalTestCase) -> None:
    """Evaluate multi-turn NPC conversations on role adherence, knowledge retention, and completeness."""
    assert_test(
        test_case=test_case,
        metrics=CONVERSATIONAL_METRICS,
    )
