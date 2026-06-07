import os
import sys
from pathlib import Path

# Add project root and tests/evals to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "evals"))

import pytest
from deepeval import assert_test
from deepeval.test_case import ConversationalTestCase, LLMTestCase, Turn

_DEEPEVAL_LIVE_URL = os.getenv("DEEPEVAL_LIVE_MODEL_URL", "http://localhost:11434").strip()
os.environ["DEEPEVAL_OLLAMA_MODEL"] = "qwen2.5:7b"
os.environ["LLMUNITY_AGENT_MODEL"] = "qwen2.5:7b"

# Ensure the Ollama judge uses the configured live URL when evaluating.
os.environ.setdefault("DEEPEVAL_OLLAMA_BASE_URL", _DEEPEVAL_LIVE_URL)

from metrics import CONVERSATIONAL_METRICS, RAG_QUALITY_METRICS

from src.core.runtime.history_guide_agent import run_history_guide

# Tracing support
try:
    import deepeval.tracing

    DEEPEVAL_TRACING_AVAILABLE = True
except ImportError:
    DEEPEVAL_TRACING_AVAILABLE = False


def test_history_guide_rag_single_turn():
    """Test single-turn RAG evaluation with targeted snippet context."""
    query = "What impact did the printing press have on Europe?"

    # Run our LangGraph agent
    actual_output = run_history_guide(query)

    # Use the targeted snippet from the primer for higher relevancy scores
    expected_context = [
        "The modern era was unlocked by the Renaissance and Reformation, "
        "where the printing press drastically scaled information access."
    ]

    # Construct the DeepEval test case
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
        context=expected_context,
        name="LangGraph RAG Single-Turn Test",
    )

    # Run assertions with RAG metrics
    assert_test(test_case, RAG_QUALITY_METRICS)


def test_history_guide_rag_multi_turn():
    """Test multi-turn conversational RAG evaluation."""
    queries = [
        "Tell me about Julius Caesar.",
        "What were his greatest military achievements?",
        "How did he influence Roman governance?",
    ]

    # Use targeted Roman context
    reference_context = [
        "Classical antiquity established foundational models of government: "
        "Greek democratic experiments and Roman republican systems. Julius Caesar "
        "played a pivotal role in the transition from Republic to Empire."
    ]

    # Run multi-turn conversation and build turns
    turns = []
    for query in queries:
        response = run_history_guide(query)
        turns.append(Turn(role="user", content=query))
        turns.append(Turn(role="assistant", content=response, retrieval_context=reference_context))

    # Build proper ConversationalTestCase
    test_case = ConversationalTestCase(
        turns=turns,
        name="LangGraph RAG Multi-Turn Test",
        chatbot_role="assistant",
    )

    # Run conversational metrics
    assert_test(test_case, CONVERSATIONAL_METRICS)


def test_history_guide_rag_with_tracing():
    """Test RAG with DeepEval tracing enabled for observability."""
    if not DEEPEVAL_TRACING_AVAILABLE:
        pytest.skip("DeepEval tracing not available")

    # Configure tracing
    try:
        from src.core.tracing.deepeval_tracing import configure_tracing

        configure_tracing()
    except ImportError:
        pass

    query = "What was the Byzantine Empire?"
    actual_output = run_history_guide(query)

    expected_context = [
        "The medieval period was characterized by the survival and evolution "
        "of the eastern Roman Empire in Byzantium."
    ]

    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
        context=expected_context,
        name="LangGraph RAG with Tracing",
    )

    # Tracing is automatically recorded in DeepEval spans
    assert_test(test_case, RAG_QUALITY_METRICS)
