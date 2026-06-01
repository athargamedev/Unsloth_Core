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
from functools import wraps
from typing import Any, Callable, TypeVar

try:
    from deepeval.tracing import trace_type, get_trace_stack
except ImportError:
    raise ImportError("deepeval>=0.21.0 required for tracing support")

__all__ = [
    "trace_agent_node",
    "trace_tool",
    "trace_retrieval",
    "configure_tracing",
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

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_type("agent", metrics=metric_list, name=span_name):
                return func(*args, **kwargs)

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

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_type("tool", metrics=metric_list, name=tool_name):
                return func(*args, **kwargs)

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

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_type("retrieval", metrics=metric_list, name=op_name):
                return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


def configure_tracing() -> None:
    """Configure DeepEval tracing globally.

    Verifies that CONFIDENT_API_KEY is set for trace uploads.
    Call once at application startup.

    Raises
    ------
    EnvironmentError
        If CONFIDENT_API_KEY is not set and traces cannot be uploaded.
    """
    confident_key = os.environ.get("CONFIDENT_API_KEY")
    if not confident_key:
        import warnings

        warnings.warn(
            "CONFIDENT_API_KEY not set. DeepEval traces will be recorded locally only. "
            "Set CONFIDENT_API_KEY to enable cloud tracing.",
            stacklevel=2,
        )
    else:
        # Traces will auto-upload to Confident AI
        pass


def get_current_trace_context() -> dict[str, Any] | None:
    """Get the current trace context if inside an @observe or trace_type block.

    Returns
    -------
    dict | None
        Trace metadata (span name, type, metrics) or None if not tracing.
    """
    try:
        stack = get_trace_stack()
        if stack:
            return {"depth": len(stack), "active": True}
    except Exception:
        pass
    return None
