from src.core.runtime import chef_assistant_agent as agent


def test_chef_trace_metadata_uses_thread_dialogue_id():
    meta = agent.build_chef_assistant_trace_metadata(
        query="How do I dice an onion safely?",
        dialogue_id="chef-thread-1",
        model_name="qwen2.5:7b",
        base_url="http://localhost:11434",
    )

    assert meta["npc_key"] == "chef_assistant"
    assert meta["technique"] == "runtime"
    assert meta["category"] == "dialogue"
    assert meta["turn_type"] == "conversational"
    assert meta["dialogue_id"] == "chef-thread-1"
    assert meta["runtime"] == "direct_ollama"


def test_run_chef_assistant_updates_trace_and_invokes_model(monkeypatch):
    calls = {}

    class FakeResponse:
        content = (
            "Use a claw grip. Keep the knife tip steady. Cut slowly. Save the speed for later."
        )

    class FakeModel:
        def __init__(self, **kwargs):
            calls["model_kwargs"] = kwargs

        def invoke(self, messages):
            calls["messages"] = messages
            return FakeResponse()

    monkeypatch.setattr(agent, "ChatOllama", FakeModel)
    monkeypatch.setattr(agent, "configure_tracing", lambda: calls.setdefault("configured", True))
    monkeypatch.setattr(
        agent, "update_current_span", lambda **kwargs: calls.setdefault("span", kwargs)
    )
    monkeypatch.setattr(
        agent, "update_current_trace", lambda **kwargs: calls.setdefault("trace", kwargs)
    )

    result = agent.run_chef_assistant("How do I dice an onion safely?", dialogue_id="chef-thread-1")

    assert result == "Use a claw grip. Keep the knife tip steady. Cut slowly."
    assert calls["configured"] is True
    assert calls["span"]["metadata"]["runtime_guard_applied"] is True
    assert calls["span"]["metadata"]["runtime_guard_raw_sentences"] == 4
    assert calls["trace"]["thread_id"] == "chef-thread-1"
    assert calls["trace"]["output"] == result
    assert "safe, practical cooking assistant" in calls["messages"][0]["content"]
