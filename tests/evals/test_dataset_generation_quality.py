"""DeepEval checks for generated NPC SFT dataset quality.

This suite evaluates existing workspace JSONL data instead of invoking the
runtime chatbot. It stays on the dataset-specific metrics so it can run inside
the build loop before committing to expensive training runs; broader RAG,
safety, and conversational metrics stay in the live NPC model eval suite.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
from pathlib import Path

import deepeval
import pytest
from deepeval import assert_test
from deepeval.dataset import EvaluationDataset
from deepeval.test_case import LLMTestCase
from deepeval.test_run import global_test_run_manager

PULLED_DATASET: EvaluationDataset | None = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import DATASET_QUALITY_METRICS

# ---------------------------------------------------------------------------
# Gate: only activate when DEEPEVAL_DATASET_LIVE is set
# ---------------------------------------------------------------------------

_DATASET_LIVE = os.getenv("DEEPEVAL_DATASET_LIVE", "").strip()
if not _DATASET_LIVE:
    pytest.skip(
        "Set DEEPEVAL_DATASET_LIVE=1 to activate dataset quality evaluation",
        allow_module_level=True,
    )

if os.getenv("DEEPEVAL_DISABLE_CONFIDENT_UPLOAD", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}:
    global_test_run_manager.disable_request = True

DEFAULT_NPCS = ("history_guide", "chef_assistant")
DEFAULT_CATEGORIES = ("identity", "teaching", "dialogue", "quest", "refusal")
DEFAULT_TECHNIQUE = "template"


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _dataset_max_workers() -> int:
    """Return the dataset gate worker count.

    Local Ollama judges are typically the bottleneck on the 6GB workstation, so
    the safe default is sequential execution. Parallelism can be enabled
    explicitly for hosted judges or larger local endpoints.
    """
    raw_workers = (
        os.getenv("DEEPEVAL_DATASET_MAX_WORKERS")
        or os.getenv("DEEPEVAL_MODEL_MAX_WORKERS")
        or os.getenv("DEEPEVAL_MAX_WORKERS")
    )
    if not raw_workers:
        return 1

    try:
        workers = int(raw_workers)
    except ValueError:
        return 1

    if workers < 1:
        return 1

    return workers


def _load_spec(npc_key: str) -> dict:
    candidates = [
        PROJECT_ROOT / "data" / "npcs" / "specs" / f"{npc_key}.json",
        PROJECT_ROOT / "subjects" / "NPC_specs" / f"{npc_key}.json",
    ]
    for path in candidates:
        if path.exists():
            with path.open() as f:
                return json.load(f)
    raise FileNotFoundError(
        f"No spec found for {npc_key}; checked: {', '.join(str(p) for p in candidates)}"
    )


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
    candidates = [
        PROJECT_ROOT / "data" / "datasets" / npc_key / technique / "train_clean.jsonl",
        PROJECT_ROOT / "subjects" / "datasets" / npc_key / technique / "train_clean.jsonl",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    rows = []
    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            row = json.loads(line)
            row["_line_number"] = line_number
            row["_path"] = str(path.relative_to(PROJECT_ROOT))
            rows.append(row)
    return rows


def _build_cases() -> list[LLMTestCase]:
    pull_alias = os.getenv("DEEPEVAL_DATASET_PULL_ALIAS", "").strip()
    if pull_alias:
        api_key = os.getenv("CONFIDENT_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "CONFIDENT_API_KEY environment variable is not set. Cannot run pull-based evaluation."
            )

        global PULLED_DATASET
        from deepeval.dataset import EvaluationDataset

        dataset = EvaluationDataset()
        try:
            dataset.pull(alias=pull_alias)
        except Exception as exc:
            raise ValueError(
                f"Failed to pull dataset '{pull_alias}' from Confident AI: {exc}"
            ) from exc

        if not dataset.goldens:
            raise ValueError(f"Pulled dataset '{pull_alias}' is empty or contains no goldens.")

        PULLED_DATASET = dataset
        cases = []
        for idx, golden in enumerate(dataset.goldens):
            metadata = getattr(golden, "additional_metadata", {}) or {}
            if not isinstance(metadata, dict):
                metadata = {}
            actual_output = golden.actual_output or golden.expected_output or ""
            context = golden.context or []
            npc_key = metadata.get("npc_key", "unknown")
            category = metadata.get("category", "unknown")
            cases.append(
                LLMTestCase(
                    name=f"{npc_key}:{category}:{idx}",
                    input=golden.input,
                    actual_output=actual_output,
                    context=context,
                    retrieval_context=context,
                    metadata=metadata,
                    tags=[npc_key, category],
                )
            )
        return cases

    npc_keys = _csv_env("DEEPEVAL_DATASET_NPC_KEYS", DEFAULT_NPCS)
    categories = _csv_env("DEEPEVAL_DATASET_CATEGORIES", DEFAULT_CATEGORIES)
    technique = os.getenv("DEEPEVAL_DATASET_TECHNIQUE", DEFAULT_TECHNIQUE)
    per_category = int(os.getenv("DEEPEVAL_DATASET_CASES_PER_CATEGORY", "1"))
    cases = []

    for npc_key in npc_keys:
        spec = _load_spec(npc_key)
        reference_doc = _load_reference_doc(spec)
        selected_by_category = dict.fromkeys(categories, 0)

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


@deepeval.log_hyperparameters
def log_hyperparameters():
    return {
        "judge_model": os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b"),
        "judge_provider": os.getenv("DEEPEVAL_JUDGE_PROVIDER", "ollama"),
        "temperature": os.getenv("DEEPEVAL_OLLAMA_TEMPERATURE", "0.3"),
        "technique": os.getenv("DEEPEVAL_DATASET_TECHNIQUE", "template"),
        "pull_alias": os.getenv("DEEPEVAL_DATASET_PULL_ALIAS", ""),
    }


TEST_CASES = _build_cases()


def test_generated_dataset_quality():
    if not TEST_CASES:
        pytest.skip("No test cases generated.")

    def evaluate_case(test_case: LLMTestCase):
        if PULLED_DATASET is not None:
            try:
                PULLED_DATASET.add_test_case(test_case)
            except Exception:
                pass
        try:
            assert_test(test_case=test_case, metrics=DATASET_QUALITY_METRICS)
            return None
        except Exception as exc:
            return test_case.name, str(exc)

    max_workers = _dataset_max_workers()
    if max_workers == 1:
        results = [evaluate_case(test_case) for test_case in TEST_CASES]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(evaluate_case, TEST_CASES))

    failures = [res for res in results if res is not None]

    if failures:
        msg_parts = [f"Dataset quality evaluation failed with {len(failures)} error(s):"]
        for name, err in failures:
            msg_parts.append(f"\n--- Failure in case '{name}' ---")
            msg_parts.append(err)
        raise AssertionError("\n".join(msg_parts))
