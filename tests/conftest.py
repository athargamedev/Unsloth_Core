import os

import pytest

# Attempt to clear deepeval tracing state between tests to prevent ValueError leaks
try:
    from deepeval.tracing import trace_manager
except ImportError:
    trace_manager = None


@pytest.fixture(autouse=True)
def clear_deepeval_tracing():
    """Resets DeepEval's global TraceManager state to prevent leakage between tests."""
    if trace_manager:
        # Reset internal maps and stacks
        trace_manager.active_traces = {}
        trace_manager.trace_stack = []
    yield
    if trace_manager:
        trace_manager.active_traces = {}
        trace_manager.trace_stack = []


@pytest.fixture(autouse=True)
def set_env_vars():
    """Ensure required environment variables are set for tests."""
    os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
    # We use qwen2.5:7b as the local default judge for evaluations
    if "DEEPEVAL_JUDGE_MODEL" not in os.environ:
        os.environ["DEEPEVAL_JUDGE_MODEL"] = "qwen2.5:7b"
    yield
