from scripts.ops.ollama_model_presets import resolve_ollama_model


def test_generation_presets_resolve_expected_models():
    assert resolve_ollama_model(preset="generate-qwen25", role="generation") == "qwen2.5:7b"
    assert resolve_ollama_model(preset="generate-llama31", role="generation") == "llama3.1:8b"
    assert resolve_ollama_model(preset="generate-qwen35-exp", role="generation") == "qwen3.5:latest"


def test_judge_presets_resolve_expected_models():
    assert resolve_ollama_model(preset="judge-qwen25", role="judge") == "qwen2.5:7b"
    assert resolve_ollama_model(preset="judge-llama31-exp", role="judge") == "llama3.1:8b"
    assert resolve_ollama_model(preset="judge-qwen35-exp", role="judge") == "qwen3.5:latest"


def test_explicit_model_overrides_preset():
    assert resolve_ollama_model(preset="generate-qwen25", model="llama3.1:8b", role="generation") == "llama3.1:8b"
