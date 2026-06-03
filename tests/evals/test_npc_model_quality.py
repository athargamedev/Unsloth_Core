"""DeepEval suite for evaluating NPC model response quality.

This suite is *inactive by default*.  Set ``DEEPEVAL_LIVE_MODEL_URL`` to
activate — this makes it explicit that the tests require a running inference
endpoint (Ollama / llama-server / OpenAI-compatible API) and should not be
confused with the lightweight offline schema checks in
``test_dataset_schema.py``.

Consumes a golden dataset built by ``scripts/evaluation/build_npc_goldens.py``
and runs the same metric families used for dataset quality gating plus
conversational metrics when multi-turn goldens are available.

Environment variables:
  DEEPEVAL_LIVE_MODEL_URL         — Activate this suite (any non-empty value)
  DEEPEVAL_OLLAMA_MODEL           — Judge model name (default: qwen3)
  DEEPEVAL_OLLAMA_BASE_URL        — Ollama server URL
  DEEPEVAL_OLLAMA_TEMPERATURE     — Judge temperature
  DEEPEVAL_GOLDEN_NPC_KEYS        — Comma-separated NPC keys (default: all 4)
  DEEPEVAL_GOLDEN_CATEGORIES      — Comma-separated categories (default: all 5)
  DEEPEVAL_GOLDEN_PER_CATEGORY    — Goldens per category per NPC (default: 3)
  DEEPEVAL_GOLDEN_TECHNIQUE       — Golden dataset technique to load (default: template)
  DEEPEVAL_MODEL_MAX_WORKERS       — Optional model eval workers (default: 1; set 4 only for endpoints that support it)
  DEEPEVAL_MAX_WORKERS             — Backward-compatible fallback for model eval workers

Model quality cases run in aggregate batches so all failing case names can be
reported together.  The default is sequential because local RTX 3060/Ollama
setups are commonly overloaded by concurrent DeepEval requests.  Opt in to
parallelism with ``DEEPEVAL_MODEL_MAX_WORKERS=4`` (or ``DEEPEVAL_MAX_WORKERS``)
when the target endpoint is provisioned for it.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import traceback
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn

# ---------------------------------------------------------------------------
# Gate: only activate when DEEPEVAL_LIVE_MODEL_URL is set
# ---------------------------------------------------------------------------

_LIVE_URL = os.getenv("DEEPEVAL_LIVE_MODEL_URL", "").strip()
if not _LIVE_URL:
    pytest.skip(
        "Set DEEPEVAL_LIVE_MODEL_URL to activate model evaluation",
        allow_module_level=True,
    )

# Set default judge model *before* importing metrics so the module-level
# JUDGE_MODEL picks it up when this is the first metrics import.
os.environ.setdefault("DEEPEVAL_OLLAMA_MODEL", "qwen3")
os.environ.setdefault("DEEPEVAL_OLLAMA_BASE_URL", _LIVE_URL)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_TECHNIQUE = os.getenv("DEEPEVAL_GOLDEN_TECHNIQUE", "template").strip() or "template"
GOLDENS_PATH = PROJECT_ROOT / "tests" / "evals" / ".dataset" / f"npc_goldens_{GOLDEN_TECHNIQUE}.json"
LEGACY_GOLDENS_PATH = PROJECT_ROOT / "tests" / "evals" / ".dataset" / "npc_goldens.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import (
    CONVERSATIONAL_METRICS,
    DATASET_QUALITY_METRICS,
    RAG_QUALITY_METRICS,
    SAFETY_METRICS,
)

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


def _model_max_workers() -> int:
    """Parse optional DeepEval model concurrency, defaulting to sequential-safe execution."""
    raw_workers = os.getenv("DEEPEVAL_MODEL_MAX_WORKERS") or os.getenv("DEEPEVAL_MAX_WORKERS")
    if not raw_workers:
        return 1

    try:
        workers = int(raw_workers)
    except ValueError:
        return 1

    if workers < 1:
        return 1

    return workers


def _load_goldens() -> list[dict]:
    """Load the golden dataset from the technique-scoped path or legacy fallback."""
    selected_path = GOLDENS_PATH if GOLDENS_PATH.exists() else LEGACY_GOLDENS_PATH
    if not selected_path.exists():
        raise FileNotFoundError(
            f"Golden dataset not found at {GOLDENS_PATH} or legacy fallback {LEGACY_GOLDENS_PATH}.\n"
            f"Run: python scripts/evaluation/build_npc_goldens.py"
        )
    with selected_path.open(encoding="utf-8") as f:
        return json.load(f)


def _is_single_turn(golden: dict) -> bool:
    """True if this golden is a single-turn (input/output) entry."""
    return "conversation" not in golden


def _matches_filter(golden: dict, npc_keys: tuple[str, ...], categories: tuple[str, ...]) -> bool:
    """Check whether a golden matches the NPC-key and category filters."""
    meta = golden.get("metadata", {})
    golden_technique = str(meta.get("technique", "")).strip()
    if golden_technique and golden_technique != GOLDEN_TECHNIQUE:
        return False
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

def _case_name(test_case: LLMTestCase | ConversationalTestCase) -> str:
    """Return a stable display name for failure aggregation."""
    return str(getattr(test_case, "name", "unnamed"))


def _evaluate_case(
    test_case: LLMTestCase | ConversationalTestCase,
    metrics: list,
) -> tuple[str, str] | None:
    """Run one DeepEval case and return failure details, if any."""
    try:
        assert_test(test_case=test_case, metrics=metrics)
    except AssertionError as exc:
        return _case_name(test_case), f"Metric assertion failed:\n{exc}"
    except Exception as exc:
        exception_name = type(exc).__name__
        return (
            _case_name(test_case),
            f"Unexpected {exception_name}: {exc}\n\nTraceback:\n{traceback.format_exc()}",
        )
    return None


def _assert_cases_concurrently(
    test_cases: list[LLMTestCase] | list[ConversationalTestCase],
    metrics: list,
    suite_name: str,
) -> None:
    """Evaluate DeepEval cases with configured workers and aggregate named failures."""
    if not test_cases:
        pytest.skip(f"No {suite_name} test cases generated.")

    def evaluate_case(test_case: LLMTestCase | ConversationalTestCase) -> tuple[str, str] | None:
        return _evaluate_case(test_case, metrics)

    max_workers = _model_max_workers()
    if max_workers == 1:
        results = [evaluate_case(test_case) for test_case in test_cases]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(evaluate_case, test_cases))

    failures = [result for result in results if result is not None]
    if not failures:
        return

    msg_parts = [f"{suite_name} evaluation failed with {len(failures)} error(s):"]
    for name, error in failures:
        msg_parts.append(f"\n--- Failure in case '{name}' ---")
        msg_parts.append(error)
    raise AssertionError("\n".join(msg_parts))


def test_npc_single_turn_responses() -> None:
    """Evaluate single-turn NPC responses on quality, RAG faithfulness, and safety."""
    _assert_cases_concurrently(
        test_cases=SINGLE_TURN_CASES,
        metrics=DATASET_QUALITY_METRICS + RAG_QUALITY_METRICS + SAFETY_METRICS,
        suite_name="Single-turn NPC response",
    )


def test_npc_conversational_responses() -> None:
    """Evaluate multi-turn NPC conversations on role adherence, knowledge retention, and completeness."""
    _assert_cases_concurrently(
        test_cases=MULTI_TURN_CASES,
        metrics=CONVERSATIONAL_METRICS,
        suite_name="Conversational NPC response",
    )
