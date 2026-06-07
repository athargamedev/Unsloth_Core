from src.core.dataset.ollama_prompts import (
    build_category_generation_prompt,
    build_generation_prompt,
    clean_generic_filler,
    contains_prompt_leak,
)


def test_prompt_helpers():
    prompt = build_category_generation_prompt("identity", "artifact use", "Guide")
    assert "Guide" in prompt
    assert "history" in prompt
    assert clean_generic_filler(
        "Once you understand this, everything falls into place.", "artifact use"
    )
    assert not contains_prompt_leak("talk about history")


def test_generation_prompt_uses_resolved_category_constraints():
    prompt = build_generation_prompt(
        npc_name="ChefAssistant",
        system_prompt="Cook safely.",
        setting="Kitchen",
        relationship="Home cook",
        category="teaching",
        concept_str="knife skills",
        category_prompt="Teach knife skills.",
        grounding="",
        player_role="home cook",
        min_sentences=1,
        max_sentences=3,
        max_chars=800,
        min_words=35,
        max_words=55,
        json_shape='"user": "...", "assistant": "..."',
    )
    assert "Speak 1-3 sentences" in prompt
    assert "Target 35-55 words" in prompt
