#!/usr/bin/env python3
"""Shared dataset contract helpers for NPC generation, validation, and eval.

This module centralizes the supported dataset categories, minimum example counts,
expected distribution helpers, and light-weight JSONL dataset summaries so the
pipeline can reason about structure and coverage with the same contract data in
multiple stages.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SUPPORTED_DATASET_CATEGORIES: tuple[str, ...] = ("identity", "teaching", "dialogue", "quest", "refusal")
MIN_DATASET_EXAMPLES_PER_CATEGORY: dict[str, int] = {
    "identity": 8,
    "teaching": 32,
    "dialogue": 16,
    "quest": 8,
    "refusal": 8,
}
VALID_DIFFICULTY_LEVELS: tuple[str, ...] = ("beginner", "intermediate", "advanced")


def expected_examples_per_category(spec: dict[str, Any] | None = None) -> dict[str, int]:
    """Return the target examples-per-category contract for a spec.

    If the spec includes an explicit `dataset.examples_per_category` mapping, use
    that. Otherwise fall back to the minimum generation-ready contract.
    """
    if isinstance(spec, dict):
        dataset = spec.get("dataset")
        if isinstance(dataset, dict):
            examples = dataset.get("examples_per_category")
            if isinstance(examples, dict) and examples:
                resolved: dict[str, int] = {}
                for category in SUPPORTED_DATASET_CATEGORIES:
                    value = examples.get(category, 0)
                    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                        resolved[category] = value
                    else:
                        resolved[category] = MIN_DATASET_EXAMPLES_PER_CATEGORY[category]
                return resolved
    return dict(MIN_DATASET_EXAMPLES_PER_CATEGORY)


def file_sha256(path: str | Path) -> str | None:
    """Return a stable content hash for a file when it exists."""
    file_path = Path(path)
    if not file_path.exists():
        return None

    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _assistant_text(record: dict[str, Any]) -> str:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return ""
    return "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, dict) and message.get("role") == "assistant" and message.get("content")
    ).strip()


def _text_density(text: str) -> dict[str, int]:
    words = re.findall(r"\b[\w'-]+\b", text or "")
    sentences = re.findall(r"[^.!?]+[.!?]", text or "")
    return {
        "words": len(words),
        "sentences": len(sentences) or (1 if (text or "").strip() else 0),
        "chars": len(text or ""),
    }


def _summarize_density(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "avg": 0.0, "min": 0, "max": 0}
    ordered = sorted(values)
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "min": ordered[0],
        "max": ordered[-1],
    }


def generation_request_counts_for_training_targets(
    target_counts: dict[str, int],
    *,
    val_split: float,
    include_validation: bool,
) -> dict[str, int]:
    """Inflate generation requests so the training split still meets targets.

    Subject specs describe the useful training rows needed per category. The
    generators also hold out a stratified validation split, so requesting exactly
    the spec target would make the train set underfill the same contract.
    """
    requests: dict[str, int] = {}
    for category, target_value in target_counts.items():
        target = max(0, int(target_value or 0))
        requested = target
        if include_validation and target > 0 and val_split > 0:
            while requested > 1:
                held_out = max(1, min(requested - 1, int(requested * val_split)))
                if requested - held_out >= target:
                    break
                requested += 1
        requests[category] = requested
    return requests


def summarize_jsonl_dataset(jsonl_path: str | Path) -> dict[str, Any]:
    """Summarize category/difficulty/concept distribution from a JSONL dataset."""
    path = Path(jsonl_path)
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "content_sha256": file_sha256(path),
        "total": 0,
        "by_category": {},
        "by_difficulty": {},
        "by_split": {},
        "by_concept": {},
        "unknown_rows": 0,
        "assistant_density": {
            "words": {"count": 0, "avg": 0.0, "min": 0, "max": 0},
            "sentences": {"count": 0, "avg": 0.0, "min": 0, "max": 0},
            "chars": {"count": 0, "avg": 0.0, "min": 0, "max": 0},
            "by_category": {},
        },
    }
    if not path.exists():
        return summary

    by_category: Counter[str] = Counter()
    by_difficulty: Counter[str] = Counter()
    by_split: Counter[str] = Counter()
    by_concept: Counter[str] = Counter()
    density_words: list[int] = []
    density_sentences: list[int] = []
    density_chars: list[int] = []
    density_by_category: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"words": [], "sentences": [], "chars": []})
    unknown_rows = 0

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                unknown_rows += 1
                continue
            metadata = record.get("metadata") if isinstance(record, dict) else None
            if not isinstance(metadata, dict):
                unknown_rows += 1
                continue
            category = metadata.get("category")
            if isinstance(category, str) and category:
                by_category[category] += 1
            difficulty = metadata.get("difficulty")
            if isinstance(difficulty, str) and difficulty:
                by_difficulty[difficulty] += 1
            split = metadata.get("split")
            if isinstance(split, str) and split:
                by_split[split] += 1
            concept = metadata.get("concept")
            if isinstance(concept, str) and concept:
                by_concept[concept] += 1
            assistant_density = _text_density(_assistant_text(record))
            density_words.append(assistant_density["words"])
            density_sentences.append(assistant_density["sentences"])
            density_chars.append(assistant_density["chars"])
            density_category = category if isinstance(category, str) and category else "unknown"
            density_by_category[density_category]["words"].append(assistant_density["words"])
            density_by_category[density_category]["sentences"].append(assistant_density["sentences"])
            density_by_category[density_category]["chars"].append(assistant_density["chars"])
            summary["total"] += 1

    summary["by_category"] = dict(sorted(by_category.items()))
    summary["by_difficulty"] = dict(sorted(by_difficulty.items()))
    summary["by_split"] = dict(sorted(by_split.items()))
    summary["by_concept"] = dict(sorted(by_concept.items(), key=lambda item: (-item[1], item[0])))
    summary["assistant_density"] = {
        "words": _summarize_density(density_words),
        "sentences": _summarize_density(density_sentences),
        "chars": _summarize_density(density_chars),
        "by_category": {
            category: {
                "words": _summarize_density(values["words"]),
                "sentences": _summarize_density(values["sentences"]),
                "chars": _summarize_density(values["chars"]),
            }
            for category, values in sorted(density_by_category.items())
        },
    }
    summary["unknown_rows"] = unknown_rows
    return summary


def calculate_distribution_gaps(
    expected: dict[str, int],
    observed: dict[str, int],
) -> list[dict[str, Any]]:
    """Return underfilled or missing categories relative to the expected counts."""
    gaps: list[dict[str, Any]] = []
    for category in SUPPORTED_DATASET_CATEGORIES:
        target = int(expected.get(category, 0) or 0)
        actual = int(observed.get(category, 0) or 0)
        if actual < target:
            gaps.append(
                {
                    "category": category,
                    "target": target,
                    "actual": actual,
                    "shortfall": target - actual,
                }
            )
    return gaps


def dataset_contract_from_spec(spec: dict[str, Any] | None) -> dict[str, Any]:
    """Build a compact machine-readable contract block from a subject spec."""
    contract = {
        "supported_categories": list(SUPPORTED_DATASET_CATEGORIES),
        "minimum_examples_per_category": dict(MIN_DATASET_EXAMPLES_PER_CATEGORY),
        "expected_examples_per_category": expected_examples_per_category(spec),
        "valid_difficulty_levels": list(VALID_DIFFICULTY_LEVELS),
    }
    if isinstance(spec, dict):
        contract["spec_npc_key"] = spec.get("npc_key")
        contract["reference_doc"] = spec.get("reference_doc")
        dataset = spec.get("dataset")
        if isinstance(dataset, dict):
            contract["technique"] = dataset.get("technique")
    return contract
