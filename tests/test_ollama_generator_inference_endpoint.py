from __future__ import annotations


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_ollama_generator_can_route_chat_through_inference_server(monkeypatch):
    import src.core.dataset.generate_dataset as gdo

    posts = []

    def fake_post(url, json, timeout):
        posts.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse({"ok": True, "message": {"content": "  generated row  "}})

    monkeypatch.setattr(gdo.requests, "post", fake_post)

    generator = gdo.OllamaGeneratorV2(
        model="qwen2.5:7b",
        url="http://localhost:11434/api/chat",
        inference_server_url="http://127.0.0.1:8765/",
        max_retries=1,
    )

    result = generator.generate(
        "system prompt", "user prompt", temperature=0.4, max_tokens=99, json_format=True
    )

    assert result == "generated row"
    assert posts[0]["url"] == "http://127.0.0.1:8765/chat"
    assert posts[0]["json"]["model"] == "qwen2.5:7b"
    assert posts[0]["json"]["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert posts[0]["json"]["format"] == "json"
    assert posts[0]["json"]["options"]["temperature"] == 0.4
    assert posts[0]["json"]["options"]["num_predict"] == 99
