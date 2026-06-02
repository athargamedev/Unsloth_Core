from src.core.tracing import deepeval_tracing as tracing


def test_trace_type_uses_supported_span_names():
    assert tracing._normalize_span_type("retrieval") == "retriever"
    assert tracing._normalize_span_type("retriever") == "retriever"
    assert tracing._normalize_span_type("agent") == "agent"
    assert tracing._normalize_span_type("llm") == "llm"
    assert tracing._normalize_span_type("tool") == "tool"


def test_trace_decorators_preserve_function_results():
    @tracing.trace_agent_node(name="agent-test")
    def agent(value):
        return {"ok": value}

    @tracing.trace_tool(name="tool-test")
    def tool(value):
        return value + 1

    @tracing.trace_retrieval(name="retriever-test")
    def retriever(query):
        return [query]

    assert agent(1) == {"ok": 1}
    assert tool(1) == 2
    assert retriever("x") == ["x"]


def test_build_span_metadata_is_classifer_safe():
    metadata = tracing.build_span_metadata(
        span_type="retrieval",
        span_name="reference_lookup",
        metrics=["faithfulness"],
        extra={"npc_key": "history_guide"},
    )
    assert metadata["span_type"] == "retriever"
    assert metadata["span_name"] == "reference_lookup"
    assert metadata["metrics"] == ["faithfulness"]
    assert metadata["npc_key"] == "history_guide"
