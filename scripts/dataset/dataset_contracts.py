#!/usr/bin/env python3
"""Shared dataset contract helpers for NPC generation, validation, and eval.

This module centralizes the supported dataset categories, minimum example counts,
expected distribution helpers, and light-weight JSONL dataset summaries so the
pipeline can reason about structure and coverage with the same contract data in
multiple stages.
"""

from __future__ import annotations

import json
from collections import Counter
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


def summarize_jsonl_dataset(jsonl_path: str | Path) -> dict[str, Any]:
    """Summarize category/difficulty/concept distribution from a JSONL dataset."""
    path = Path(jsonl_path)
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "total": 0,
        "by_category": {},
        "by_difficulty": {},
        "by_split": {},
        "by_concept": {},
        "unknown_rows": 0,
    }
    if not path.exists():
        return summary

    by_category: Counter[str] = Counter()
    by_difficulty: Counter[str] = Counter()
    by_split: Counter[str] = Counter()
    by_concept: Counter[str] = Counter()
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
            summary["total"] += 1

    summary["by_category"] = dict(sorted(by_category.items()))
    summary["by_difficulty"] = dict(sorted(by_difficulty.items()))
    summary["by_split"] = dict(sorted(by_split.items()))
    summary["by_concept"] = dict(sorted(by_concept.items(), key=lambda item: (-item[1], item[0])))
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
