#!/usr/bin/env python3
"""Project-specific Confident AI insight helpers for Unsloth_Core.

These helpers turn local dataset/eval artifacts into actionable Confident AI
payloads plus a local ``confident_insights.json`` file.  The goal is not just
cloud upload; it is root-cause routing for the NPC LoRA workflow.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_NAME = "Unsloth_Core"
DATASET_REPAIR_METRIC_COLLECTION = {
    "name": "unsloth-core-dataset-repair",
    "include": [
        "Persona and Category Fit",
        "Training Usefulness and Specificity",
        "Grounding and Specificity",
        "Runtime Constraint Fit",
    ],
}

_COMPONENT_ACTIONS = {
    "judge_runner": "rerun a smaller semantic gate or fix judge/Ollama availability before changing data",
    "spec_contract": "tighten identity/refusal contract templates in spec or generator prompt",
    "generator_grounding": "repair reference-grounded prompt/context for weak concepts before training",
    "runtime_constraints": "shorten generation templates and enforce Unity dialogue limits before training",
    "sanitizer_metadata": "fix metadata/category/source fields before semantic judging",
    "dataset_distribution": "top up missing categories/concepts, then sanitize and re-gate",
    "evaluation_parser": "inspect DeepEval output parsing before trusting pass/fail status",
}


def classify_failure_component(failure: dict[str, Any], summary: dict[str, Any] | None = None) -> str:
    """Map one dataset/eval failure to the project component that should act."""
    summary = summary or {}
    metric = failure.get("metric") or {}
    metadata = failure.get("metadata") or {}
    category = str(metadata.get("category") or "").lower()
    metric_name = str(metric.get("name") or failure.get("metric_name") or "").lower()
    reason = str(metric.get("reason") or failure.get("reason") or "").lower()
    score = metric.get("score", failure.get("score"))

    if score is None or summary.get("status") == "inconclusive" or "timeout" in reason or "null" in reason:
        return "judge_runner"
    if summary.get("distribution_gaps") or "distribution" in reason or "missing category" in reason:
        return "dataset_distribution"
    if "metadata" in reason or "source" in reason or category in {"", "unknown"}:
        return "sanitizer_metadata"
    if category in {"identity", "refusal"} or "persona" in metric_name or "identity" in reason or "refusal" in reason:
        return "spec_contract"
    if "brevity" in reason or "too long" in reason or "sentence" in reason or "constraint" in metric_name:
        return "runtime_constraints"
    if "generic" in reason or "ground" in reason or "specific" in reason or "usefulness" in metric_name:
        return "generator_grounding"
    if "parse" in reason or "json" in reason:
        return "evaluation_parser"
    return "generator_grounding"


def _failure_text(failure: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = failure.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _to_confident_case(
    failure: dict[str, Any],
    *,
    npc_key: str,
    technique: str,
    summary: dict[str, Any],
) -> dict[str, Any]:
    metric = failure.get("metric") or {}
    metadata = dict(failure.get("metadata") or {})
    component = classify_failure_component(failure, summary)
    custom_columns = {
        "project": PROJECT_NAME,
        "npc_key": npc_key,
        "technique": technique,
        "component": component,
        "repair_action": _COMPONENT_ACTIONS[component],
        "category": metadata.get("category"),
        "concept": metadata.get("concept"),
        "line_number": metadata.get("line_number"),
        "metric": metric.get("name") or failure.get("metric_name"),
        "score": metric.get("score", failure.get("score")),
        "reason": metric.get("reason") or failure.get("reason"),
    }
    return {
        "name": failure.get("name") or f"{npc_key}:{metadata.get('category', 'unknown')}:{metadata.get('line_number', 'na')}",
        "input": _failure_text(failure, "input", "prompt") or failure.get("user", ""),
        "actualOutput": _failure_text(failure, "actualOutput", "actual_output", "output", "assistant"),
        "expectedOutput": metadata.get("expected_output") or metadata.get("reference_answer") or "",
        "context": metadata.get("context") or metadata.get("retrieval_context") or [],
        "customColumnKeyValues": {k: v for k, v in custom_columns.items() if v is not None},
    }


_COMPONENT_PRIORITY = {
    "judge_runner": 100,
    "generator_grounding": 90,
    "spec_contract": 80,
    "runtime_constraints": 70,
    "sanitizer_metadata": 60,
    "dataset_distribution": 50,
    "evaluation_parser": 40,
}


def _rank_actions(component_counts: Counter[str]) -> list[dict[str, Any]]:
    ranked = sorted(
        component_counts.items(),
        key=lambda item: (-item[1], -_COMPONENT_PRIORITY.get(item[0], 0), item[0]),
    )
    return [
        {"component": component, "count": count, "action": _COMPONENT_ACTIONS[component]}
        for component, count in ranked
    ]


def build_dataset_quality_insights(
    *,
    summary: dict[str, Any],
    failures: list[dict[str, Any]],
    npc_key: str,
    technique: str,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build local insight JSON and Confident AI payload for dataset quality failures."""
    cases = [
        _to_confident_case(failure, npc_key=npc_key, technique=technique, summary=summary)
        for failure in failures
    ]
    component_counts: Counter[str] = Counter(
        case["customColumnKeyValues"]["component"] for case in cases
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    identifier = f"dataset-quality:{npc_key}:{technique}:{timestamp}"
    return {
        "project": PROJECT_NAME,
        "kind": "dataset_quality_insights",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "npc_key": npc_key,
        "technique": technique,
        "status": summary.get("status"),
        "summary": summary,
        "artifact_paths": artifact_paths or {},
        "component_counts": dict(component_counts),
        "recommended_next_actions": _rank_actions(component_counts),
        "confident_payload": {
            "identifier": identifier,
            "metricCollection": DATASET_REPAIR_METRIC_COLLECTION,
            "llmTestCases": cases,
            "hyperparameters": {
                "project": PROJECT_NAME,
                "npc_key": npc_key,
                "technique": technique,
                "local_status": summary.get("status"),
            },
        },
    }


def write_dataset_quality_insights(
    *,
    output_dir: str | Path,
    summary: dict[str, Any],
    failures: list[dict[str, Any]],
    npc_key: str,
    technique: str,
    artifact_paths: dict[str, str] | None = None,
) -> Path:
    """Write ``confident_insights.json`` next to local quality artifacts."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    insights = build_dataset_quality_insights(
        summary=summary,
        failures=failures,
        npc_key=npc_key,
        technique=technique,
        artifact_paths=artifact_paths,
    )
    out_path = out_dir / "confident_insights.json"
    out_path.write_text(json.dumps(insights, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


__all__ = [
    "DATASET_REPAIR_METRIC_COLLECTION",
    "build_dataset_quality_insights",
    "classify_failure_component",
    "write_dataset_quality_insights",
]
