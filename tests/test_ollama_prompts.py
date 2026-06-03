from src.core.dataset.ollama_prompts import build_category_generation_prompt, clean_generic_filler, contains_prompt_leak


def test_prompt_helpers():
    prompt = build_category_generation_prompt("identity", "artifact use", "Guide")
    assert "Guide" in prompt
    assert "history" in prompt
    assert clean_generic_filler("Once you understand this, everything falls into place.", "artifact use")
    assert not contains_prompt_leak("talk about history")
