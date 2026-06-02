import pytest

from src.core.dataset.generate_dataset_ollama import OllamaDatasetGenerator


class FakeGenerator:
    model = "fake"

    async def generate_async(self, *args, **kwargs):
        return '{"user":"Can we talk about something unrelated?","assistant":"Sure, ask anything.","user2":"What about cars?","assistant2":"Cars are fun."}'


def history_spec():
    return {
        "npc_key": "history_guide",
        "npc_name": "HistoryGuide",
        "subject": "World history",
        "system_prompt": "You are a history guide.",
        "reference_doc": None,
        "dialogue": {"max_sentences": 5, "max_characters": 500, "allow_formatting": False},
        "concepts": [{"name": "ancient civilizations"}],
    }


@pytest.mark.asyncio
async def test_refusal_generation_drops_llm_followup_turns_after_fallback():
    generator = OllamaDatasetGenerator(history_spec(), FakeGenerator(), batch_size=1)

    row = await generator.generate_example_llm(
        "refusal",
        "topic change request",
        boundary="topic change request",
    )

    roles = [message["role"] for message in row["messages"]]
    assert roles == ["system", "user", "assistant"]
    assistant = row["messages"][-1]["content"].lower()
    assert "instead" in assistant or "i can help with" in assistant or "let's focus on" in assistant
