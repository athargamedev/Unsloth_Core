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
from metrics import JUDGE_MODEL

# We want to trace the RAG execution. 
import deepeval.tracing

def test_history_guide_rag():
    query = "What impact did the printing press have on Europe?"
    
    # Run our LangGraph agent
    # In a real setup, we would capture the retrieved context from the LangGraph state.
    # For this test, we'll run it, then mock the context extraction.
    actual_output = run_history_guide(query)
    
    # Load the expected context from the primer to check faithfulness
    primer_path = Path(__file__).resolve().parents[2] / "subjects" / "reference_docs" / "history_guide_primer.md"
    expected_context = [primer_path.read_text(encoding="utf-8")]

    # Construct the DeepEval test case
    test_case = LLMTestCase(
        input=query,
        actual_output=actual_output,
        retrieval_context=expected_context,
        name="LangGraph RAG Tool-Use Test"
    )

    # Initialize metrics using our existing Ollama judge (qwen2.5:7b)
    faithfulness = FaithfulnessMetric(threshold=0.7, model=JUDGE_MODEL, async_mode=True)
    answer_relevancy = AnswerRelevancyMetric(threshold=0.7, model=JUDGE_MODEL, async_mode=True)

    # Run assertions
    assert_test(test_case, [faithfulness, answer_relevancy])
