from pathlib import Path

from src.core.runtime import history_guide_agent as agent


def test_history_guide_primer_path_points_to_existing_reference_doc():
    assert agent.HISTORY_GUIDE_PRIMER_PATH == Path(
        "/home/athar/Projects/Unsloth_Core/data/npcs/reference_docs/history_guide_primer.md"
    )


def test_build_trace_metadata_includes_thread_and_classifier_dimensions():
    metadata = agent.build_history_guide_trace_metadata(
        query="Why did Rome fall?",
        dialogue_id="dialogue-1",
        model_name="qwen2.5:7b",
        base_url="http://localhost:11434",
    )
    assert metadata["npc_key"] == "history_guide"
    assert metadata["category"] == "dialogue"
    assert metadata["turn_type"] == "conversational"
    assert metadata["dialogue_id"] == "dialogue-1"
    assert metadata["model"] == "qwen2.5:7b"
    assert metadata["base_url"] == "http://localhost:11434"


def test_runtime_query_accepts_dialogue_id(monkeypatch):
    class Message:
        content = "Rome fell through political, military, and economic pressures."

    def fake_invoke(inputs, *args, **kwargs):
        assert inputs["dialogue_id"] == "dialogue-1"
        assert inputs["messages"][0].content == "Why did Rome fall?"
        return {"messages": [Message()]}

    monkeypatch.setattr(agent.app, "invoke", fake_invoke)

    result = agent.run_history_guide("Why did Rome fall?", dialogue_id="dialogue-1")
    assert result == Message.content
