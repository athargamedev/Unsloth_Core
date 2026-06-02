import os
import sys
from pathlib import Path

# Add project root and tests/evals to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "evals"))

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase, ConversationalTestCase, Turn
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric

_DEEPEVAL_LIVE_URL = os.getenv("DEEPEVAL_LIVE_MODEL_URL", "http://localhost:11434").strip()
os.environ["DEEPEVAL_OLLAMA_MODEL"] = "qwen2.5:7b"
os.environ["LLMUNITY_AGENT_MODEL"] = "qwen2.5:7b"

# Ensure the Ollama judge uses the configured live URL when evaluating.
os.environ.setdefault("DEEPEVAL_OLLAMA_BASE_URL", _DEEPEVAL_LIVE_URL)

from scripts.runtime.history_guide_agent import run_history_guide
from metrics import JUDGE_MODEL, CONVERSATIONAL_METRICS, RAG_QUALITY_METRICS

# Tracing support
try:
    import deepeval.tracing
    DEEPEVAL_TRACING_AVAILABLE = True
except ImportError:
    DEEPEVAL_TRACING_AVAILABLE = False


def test_history_guide_rag_single_turn():
    """Test single-turn RAG evaluation with vector search."""
    query = "What impact did the printing press have on Europe?"
    
    # Run our LangGraph agent
    actual_output = run_history_guide(query)
    
    # Load the expected context from the primer to check faithfulness
    primer_path = Path(__file__).resolve().parents[2] / "data" / "npcs" / "reference_docs" / "history_guide_primer.md"
    expected_context = [primer_path.read_text(encoding="utf-8")]

    # Construct the DeepEval test case
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
        context=expected_context,
        name="LangGraph RAG Single-Turn Test"
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
    
    # Load reference context
    primer_path = Path(__file__).resolve().parents[2] / "data" / "npcs" / "reference_docs" / "history_guide_primer.md"
    reference_context = [primer_path.read_text(encoding="utf-8")]
    
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
    
    # Configure tracing (optional; would auto-upload to Confident AI)
    try:
        from src.core.tracing.deepeval_tracing import configure_tracing
        configure_tracing()
    except ImportError:
        pass
    
    query = "What was the Byzantine Empire?"
    actual_output = run_history_guide(query)
    
    primer_path = Path(__file__).resolve().parents[2] / "data" / "npcs" / "reference_docs" / "history_guide_primer.md"
    expected_context = [primer_path.read_text(encoding="utf-8")]
    
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
        context=expected_context,
        name="LangGraph RAG with Tracing"
    )
    
    # Tracing is automatically recorded in DeepEval spans
    assert_test(test_case, RAG_QUALITY_METRICS)
