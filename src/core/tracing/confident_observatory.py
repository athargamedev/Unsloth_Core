"""Confident AI Observatory tracing helpers for Unsloth_Core NPC runtime/eval flows.

DeepEval test runs and Confident Observatory traces are different products:
- Dataset quality gates use DeepEval `assert_test` / Confident test runs.
- Runtime NPC calls use `deepeval.tracing.observe` and trace metadata/tags so Project
  Classifiers can segment weaknesses/strengths in the Observatory.

This module keeps the metadata contract stable without forcing every caller to import
DeepEval tracing at module import time.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Literal


ObservabilityUseCase = Literal[
    "dataset_quality_gate",
    "remote_dataset_eval",
    "runtime_npc_call",
    "openai_runtime_call",
    "local_llama_runtime_call",
]


def choose_observability_path(use_case: str) -> dict[str, str]:
    """Choose native DeepEval eval upload vs manual Observatory tracing.

    Classifiers in Confident Project Settings operate on Observatory traces/threads.
    They do not replace dataset quality gates or REST `/evaluate` submissions.
    """
    if use_case in {"dataset_quality_gate", "remote_dataset_eval"}:
        return {
            "path": "deepeval_test_run",
            "reason": "Dataset quality metrics belong in DeepEval/Confident test runs, not Observatory traces.",
            "classifier_scope": "Use golden custom columns and metric failures; Observatory classifiers need runtime traces.",
        }
    if use_case == "openai_runtime_call":
        return {
            "path": "native_integration_or_manual_observe",
            "reason": "Use native integration if available for provider call details; still wrap the NPC app with @observe for trace tags/metadata.",
            "classifier_scope": "Trace/thread classifiers can segment runtime outputs by NPC/category/turn_type.",
        }
    return {
        "path": "manual_observe",
        "reason": "Local Ollama/llama.cpp/Unity flows need manual @observe spans for Confident Observatory.",
        "classifier_scope": "Trace/thread classifiers can segment runtime outputs by NPC/category/turn_type.",
    }


def build_npc_trace_tags(
    *,
    npc_key: str,
    technique: str,
    category: str,
    turn_type: str,
    environment: str = "dev",
) -> list[str]:
    return [
        f"npc:{npc_key}",
        f"technique:{technique}",
        f"category:{category}",
        f"turn_type:{turn_type}",
        f"env:{environment}",
        "ucore",
    ]


def build_npc_trace_metadata(
    *,
    npc_key: str,
    technique: str,
    category: str,
    concept: str = "",
    source_path: str = "",
    line_number: int | None = None,
    turn_type: str = "single",
    classifier_hints: dict[str, Any] | None = None,
    model: str = "",
    adapter: str = "",
    dataset_alias: str = "",
    dataset_version: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "npc_key": npc_key,
        "technique": technique,
        "category": category,
        "concept": concept,
        "turn_type": turn_type,
        "source_path": source_path,
        "line_number": line_number,
        "model": model,
        "adapter": adapter,
        "dataset_alias": dataset_alias,
        "dataset_version": dataset_version,
    }
    if classifier_hints:
        metadata.update({k: v for k, v in classifier_hints.items() if k.startswith("classifier_")})
    if extra:
        metadata.update(extra)
    return {k: v for k, v in metadata.items() if v not in (None, "")}


def observe_npc_runtime_call(
    *,
    npc_key: str,
    technique: str,
    category: str,
    turn_type: str = "single",
    environment: str = "dev",
    metric_collection: str | None = None,
    metadata: dict[str, Any] | None = None,
    thread_id: str | None = None,
    user_id: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator factory for runtime NPC calls.

    Import DeepEval lazily so tests/imports do not require Confident credentials.
    The wrapped function should return the NPC text output or a dict containing
    `actual_output`/`retrieval_context` if richer output is available.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        try:
            from deepeval.tracing import observe, update_current_trace
        except Exception:
            return func

        @observe(type="agent", name=f"npc-runtime:{npc_key}", metric_collection=metric_collection)
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            tags = build_npc_trace_tags(
                npc_key=npc_key,
                technique=technique,
                category=category,
                turn_type=turn_type,
                environment=environment,
            )
            trace_metadata = build_npc_trace_metadata(
                npc_key=npc_key,
                technique=technique,
                category=category,
                turn_type=turn_type,
                extra=metadata,
            )
            output = result.get("actual_output") if isinstance(result, dict) else result
            retrieval_context = result.get("retrieval_context") if isinstance(result, dict) else None
            update_current_trace(
                name=f"{npc_key}:{category}:{turn_type}",
                tags=tags,
                metadata=trace_metadata,
                thread_id=thread_id,
                user_id=user_id,
                output=output,
                retrieval_context=retrieval_context,
            )
            return result

        return wrapper

    return decorator
