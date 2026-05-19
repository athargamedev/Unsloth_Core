"""DeepEval checks for generated NPC SFT dataset quality.

This suite evaluates existing workspace JSONL data instead of invoking the
runtime chatbot. It is intentionally small by default so it can be used inside
the build loop before committing to expensive training runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import (
    CONVERSATIONAL_METRICS,
    DATASET_QUALITY_METRICS,
    RAG_QUALITY_METRICS,
    SAFETY_METRICS,
)

DEFAULT_NPCS = ("history_guide", "chef_assistant")
DEFAULT_CATEGORIES = ("identity", "teaching", "dialogue", "quest", "refusal")
DEFAULT_TECHNIQUE = "template"


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _load_spec(npc_key: str) -> dict:
    with (PROJECT_ROOT / "subjects" / f"{npc_key}.json").open() as f:
        return json.load(f)


def _load_reference_doc(spec: dict) -> str:
    ref = spec.get("reference_doc")
    if not ref:
        return ""
    path = PROJECT_ROOT / ref
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _message(messages: list[dict], role: str) -> str:
    for message in messages:
        if message.get("role") == role:
            return str(message.get("content", ""))
    return ""


def _iter_rows(npc_key: str, technique: str) -> list[dict]:
    path = PROJECT_ROOT / "subjects" / "datasets" / npc_key / technique / "train_clean.jsonl"
    rows = []
    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            row = json.loads(line)
            row["_line_number"] = line_number
            row["_path"] = str(path.relative_to(PROJECT_ROOT))
            rows.append(row)
    return rows


def _build_cases() -> list[LLMTestCase]:
    npc_keys = _csv_env("DEEPEVAL_DATASET_NPC_KEYS", DEFAULT_NPCS)
    categories = _csv_env("DEEPEVAL_DATASET_CATEGORIES", DEFAULT_CATEGORIES)
    technique = os.getenv("DEEPEVAL_DATASET_TECHNIQUE", DEFAULT_TECHNIQUE)
    per_category = int(os.getenv("DEEPEVAL_DATASET_CASES_PER_CATEGORY", "1"))
    cases = []

    for npc_key in npc_keys:
        spec = _load_spec(npc_key)
        reference_doc = _load_reference_doc(spec)
        selected_by_category = {category: 0 for category in categories}

        for row in _iter_rows(npc_key, technique):
            metadata = row.get("metadata", {})
            category = metadata.get("category")
            if category not in selected_by_category:
                continue
            if selected_by_category[category] >= per_category:
                continue
            selected_by_category[category] += 1

            messages = row.get("messages", [])
            user_message = _message(messages, "user")
            assistant_message = _message(messages, "assistant")
            system_prompt = _message(messages, "system")
            concept = metadata.get("concept", "")

            eval_input = "\n".join(
                [
                    f"NPC: {npc_key}",
                    f"Category: {category}",
                    f"Concept: {concept}",
                    f"Difficulty: {metadata.get('difficulty')}",
                    f"User message: {user_message}",
                ]
            )
            context = [
                f"System prompt:\n{system_prompt}",
                f"Subject:\n{spec.get('subject', '')}",
                f"Reference doc:\n{reference_doc[:6000]}",
            ]
            cases.append(
                LLMTestCase(
                    name=f"{npc_key}:{category}:{row['_line_number']}",
                    input=eval_input,
                    actual_output=assistant_message,
                    context=context,
                    retrieval_context=context,
                    metadata={
                        "npc_key": npc_key,
                        "category": category,
                        "concept": concept,
                        "source_path": row["_path"],
                        "line_number": row["_line_number"],
                    },
                    tags=[npc_key, category],
                )
            )

    return cases


def _build_conversational_cases() -> list[ConversationalTestCase]:
    npc_keys = _csv_env("DEEPEVAL_DATASET_NPC_KEYS", DEFAULT_NPCS)
    categories = _csv_env("DEEPEVAL_DATASET_CATEGORIES", DEFAULT_CATEGORIES)
    technique = os.getenv("DEEPEVAL_DATASET_TECHNIQUE", DEFAULT_TECHNIQUE)
    per_category = int(os.getenv("DEEPEVAL_DATASET_CASES_PER_CATEGORY", "1"))
    cases = []

    for npc_key in npc_keys:
        selected_by_category = {category: 0 for category in categories}

        for row in _iter_rows(npc_key, technique):
            metadata = row.get("metadata", {})
            category = metadata.get("category")
            if category not in selected_by_category:
                continue
            if selected_by_category[category] >= per_category:
                continue
            selected_by_category[category] += 1

            messages = row.get("messages", [])
            turns = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    turns.append(Turn(role=role, content=content))

            if len(turns) >= 2:
                cases.append(
                    ConversationalTestCase(
                        name=f"{npc_key}:conv:{category}:{row['_line_number']}",
                        turns=turns,
                        metadata={
                            "npc_key": npc_key,
                            "category": category,
                            "source_path": row["_path"],
                            "line_number": row["_line_number"],
                        },
                        tags=[npc_key, category, "conversational"],
                    )
                )

    return cases


TEST_CASES = _build_cases()
CONVERSATIONAL_TEST_CASES = _build_conversational_cases()


@pytest.mark.parametrize("test_case", TEST_CASES, ids=lambda case: case.name)
def test_generated_dataset_row_quality(test_case: LLMTestCase):
    assert_test(test_case=test_case, metrics=DATASET_QUALITY_METRICS + RAG_QUALITY_METRICS + SAFETY_METRICS)


@pytest.mark.parametrize("test_case", CONVERSATIONAL_TEST_CASES, ids=lambda case: case.name)
def test_generated_dataset_conversational_quality(test_case: ConversationalTestCase):
    assert_test(test_case=test_case, metrics=CONVERSATIONAL_METRICS)
