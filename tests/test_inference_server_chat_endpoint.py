from __future__ import annotations


class _FakeOllamaClient:
    def __init__(self):
        self.chat_calls = []

    def chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        return {"message": {"content": "generated text"}, "done": True}


def test_inference_service_chat_normalizes_ollama_response():
    from src.core.ops.inference_server import InferenceService

    client = _FakeOllamaClient()
    service = InferenceService(client=client, default_model="qwen2.5:7b")

    result = service.chat(
        {
            "model": "qwen2.5:7b",
            "messages": [{"role": "user", "content": "hello"}],
            "options": {"temperature": 0.2},
            "format": "json",
            "keep_alive": "10m",
            "timeout": 45,
        }
    )

    assert result["ok"] is True
    assert result["model"] == "qwen2.5:7b"
    assert result["message"]["content"] == "generated text"
    assert client.chat_calls == [
        {
            "model": "qwen2.5:7b",
            "messages": [{"role": "user", "content": "hello"}],
            "format": "json",
            "options": {"temperature": 0.2},
            "keep_alive": "10m",
            "timeout": 45,
        }
    ]
