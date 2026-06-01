import os
import sys
from pathlib import Path

# Add project root and tests/evals to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "evals"))

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric

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
    primer_path = Path(__file__).resolve().parents[2] / "subjects" / "reference_docs" / "history_guide_primer.md"
    expected_context = [primer_path.read_text(encoding="utf-8")]

    # Construct the DeepEval test case
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
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
    primer_path = Path(__file__).resolve().parents[2] / "subjects" / "reference_docs" / "history_guide_primer.md"
    reference_context = [primer_path.read_text(encoding="utf-8")]
    
    # Run multi-turn conversation
    responses = []
    for query in queries:
        response = run_history_guide(query)
        responses.append(response)
    
    # Build multi-turn test case using ConversationalTestCase
    # For now, we'll test the final response in context
    final_output = "\n".join(responses)
    
    test_case = LLMTestCase(
        input="\n".join(queries),  # All queries combined
        actual_output=final_output,
        retrieval_context=reference_context,
        name="LangGraph RAG Multi-Turn Test"
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
    
    primer_path = Path(__file__).resolve().parents[2] / "subjects" / "reference_docs" / "history_guide_primer.md"
    expected_context = [primer_path.read_text(encoding="utf-8")]
    
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
        name="LangGraph RAG with Tracing"
    )
    
    # Tracing is automatically recorded in DeepEval spans
    assert_test(test_case, RAG_QUALITY_METRICS)
