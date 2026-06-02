#!/usr/bin/env python3
"""DeepEval tracing and observability setup for LangGraph agents and RAG pipelines.

Provides decorators and utilities to instrument LangGraph nodes, retrieval functions,
and model calls with DeepEval @observe for full end-to-end observability.

Usage:
    from src.core.tracing.deepeval_tracing import trace_agent_node, trace_tool, AGENT_METRICS

    @trace_agent_node(metrics=AGENT_METRICS)
    def call_model(state: AgentState):
        ...

    @trace_tool(name="search_lore")
    def search_lore(query: str) -> str:
        ...
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, TypeVar

try:
    from deepeval.tracing import (
        current_trace_context,
        observe as deepeval_observe,
        trace as deepeval_trace,
        update_current_span,
    )
except ImportError:
    current_trace_context = None  # type: ignore
    deepeval_observe = None  # type: ignore
    deepeval_trace = None  # type: ignore
    update_current_span = None  # type: ignore


def _normalize_span_type(span_type: str) -> str:
    """Normalize project names to Confident AI span types."""
    if span_type == "retrieval":
        return "retriever"
    return span_type


def build_span_metadata(
    *,
    span_type: str,
    span_name: str,
    metrics: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "span_type": _normalize_span_type(span_type),
        "span_name": span_name,
        "metrics": metrics or [],
        "prompt_version": os.environ.get("DEEPEVAL_PROMPT_VERSION", "unknown"),
    }
    if extra:
        metadata.update(extra)
    return metadata


@contextmanager
def trace_type(span_type: str, metrics: list[str] | None = None, name: str | None = None, **metadata: Any):
    """Trace a block with the current DeepEval/Confident AI context API."""
    normalized_type = _normalize_span_type(span_type)
    span_name = name or normalized_type
    span_metadata = build_span_metadata(
        span_type=normalized_type,
        span_name=span_name,
        metrics=metrics,
        extra=metadata,
    )
    if deepeval_trace is None:
        yield
        return

    with deepeval_trace(
        name=span_name,
        metadata=span_metadata,
        metric_collection=normalized_type,
    ):
        yield


__all__ = [
    "trace_agent_node",
    "trace_tool",
    "trace_retrieval",
    "configure_tracing",
    "build_span_metadata",
    "trace_type",
    "AGENT_METRICS",
    "RETRIEVAL_METRICS",
    "LLM_METRICS",
]

F = TypeVar("F", bound=Callable[..., Any])

# ─────────────────────────────────────────────────────────────────────────────
# Metric Collections for Different Spans
# ─────────────────────────────────────────────────────────────────────────────

# Metrics for agent decision-making and tool selection
AGENT_METRICS = [
    "faithfulness",  # agent reasoning is grounded in facts
    "answer_relevancy",  # agent response is relevant to query
    "hallucination",  # agent doesn't make up facts
]

# Metrics for retrieval/RAG steps
RETRIEVAL_METRICS = [
    "contextual_precision",  # retrieved context is relevant
    "contextual_recall",  # retrieved context covers the query
    "faithfulness",  # context is factual
]

# Metrics for LLM generation quality
LLM_METRICS = [
    "answer_relevancy",
    "hallucination",
    "toxicity",
    "bias",
]


# ─────────────────────────────────────────────────────────────────────────────
# Tracing Decorators
# ─────────────────────────────────────────────────────────────────────────────


def trace_agent_node(
    name: str | None = None,
    metrics: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator to trace a LangGraph agent node with DeepEval observability.

    Parameters
    ----------
    name : str, optional
        Span name (defaults to function name). Use for identifying the node.
    metrics : list[str], optional
        DeepEval metrics to attach to this span (e.g., ["faithfulness", "hallucination"]).
        Defaults to AGENT_METRICS.

    Example
    -------
    >>> @trace_agent_node(name="llm_reasoning", metrics=AGENT_METRICS)
    >>> def call_model(state: AgentState):
    ...     return model.invoke(state["messages"])
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__
        metric_list = metrics or AGENT_METRICS

        if deepeval_observe is None:
            return func

        @deepeval_observe(type="agent", name=span_name, metric_collection="agent")
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if update_current_span is not None:
                update_current_span(
                    output=result,
                    metadata=build_span_metadata(span_type="agent", span_name=span_name, metrics=metric_list),
                    name=span_name,
                    metric_collection="agent",
                )
            return result

        return wrapper  # type: ignore

    return decorator


def trace_tool(
    name: str | None = None,
    metrics: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator to trace a tool execution (retrieval, knowledge lookup, etc.).

    Parameters
    ----------
    name : str, optional
        Tool name. Displayed in DeepEval dashboard.
    metrics : list[str], optional
        Metrics to evaluate this tool's output (defaults to RETRIEVAL_METRICS).

    Example
    -------
    >>> @trace_tool(name="search_lore", metrics=RETRIEVAL_METRICS)
    >>> def search_lore(query: str) -> str:
    ...     return vector_db.search(query)
    """

    def decorator(func: F) -> F:
        tool_name = name or func.__name__
        metric_list = metrics or RETRIEVAL_METRICS

        if deepeval_observe is None:
            return func

        @deepeval_observe(type="tool", name=tool_name, metric_collection="tool")
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if update_current_span is not None:
                update_current_span(
                    output=result,
                    metadata=build_span_metadata(span_type="tool", span_name=tool_name, metrics=metric_list),
                    name=tool_name,
                    metric_collection="tool",
                )
            return result

        return wrapper  # type: ignore

    return decorator


def trace_retrieval(
    name: str | None = None,
    metrics: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator to trace retrieval operations (vector search, BM25, etc.).

    Parameters
    ----------
    name : str, optional
        Retrieval operation name.
    metrics : list[str], optional
        Metrics to evaluate retrieval quality (defaults to RETRIEVAL_METRICS).

    Example
    -------
    >>> @trace_retrieval(name="vector_search")
    >>> def retrieve_docs(query: str, k: int = 5) -> list[str]:
    ...     return vector_db.search(query, top_k=k)
    """

    def decorator(func: F) -> F:
        op_name = name or func.__name__
        metric_list = metrics or RETRIEVAL_METRICS

        if deepeval_observe is None:
            return func

        @deepeval_observe(type="retriever", name=op_name, metric_collection="retriever")
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            retrieval_context = [str(item) for item in result] if isinstance(result, list) else [str(result)]
            if update_current_span is not None:
                update_current_span(
                    output=result,
                    retrieval_context=retrieval_context,
                    metadata=build_span_metadata(span_type="retriever", span_name=op_name, metrics=metric_list),
                    name=op_name,
                    metric_collection="retriever",
                )
            return result

        return wrapper  # type: ignore

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


def configure_tracing() -> None:
    """Configure DeepEval tracing globally.

    Verifies that CONFIDENT_API_KEY is set for trace uploads and enables
    trace flushing when Confident AI is configured.
    Call once at application startup.

    Raises
    ------
    EnvironmentError
        If CONFIDENT_API_KEY is not set and traces cannot be uploaded.
    """
    from src.core.ops.env_loader import ensure_confident_api_key

    try:
        if ensure_confident_api_key():
            os.environ.setdefault("CONFIDENT_TRACE_FLUSH", "1")
        else:
            import warnings

            warnings.warn(
                "CONFIDENT_API_KEY not set. DeepEval traces will be recorded locally only. "
                "Set CONFIDENT_API_KEY to enable cloud tracing.",
                stacklevel=2,
            )
    except EnvironmentError as exc:
        import warnings

        warnings.warn(str(exc), stacklevel=2)


def get_current_trace_context() -> dict[str, Any] | None:
    """Get the current trace context if inside an active DeepEval trace."""
    try:
        if current_trace_context is not None:
            ctx = current_trace_context.get()
            if ctx is not None:
                return {
                    "active": True,
                    "context": str(ctx),
                    "span_type": getattr(ctx, "span_type", None),
                    "name": getattr(ctx, "name", None),
                }
    except Exception:
        pass
    return None
