from __future__ import annotations


def _example() -> dict:
    return {
        "messages": [
            {"role": "system", "content": "You are Chef."},
            {"role": "user", "content": "How do I know chicken is safe?"},
            {"role": "assistant", "content": "Cook chicken until the thickest part reaches 165°F."},
        ],
        "metadata": {"npc_key": "chef_assistant", "concept": "food safety"},
    }


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_llm_sanity_checker_can_use_inference_server_judge_endpoint(tmp_path, monkeypatch):
    from src.core.dataset import sanitize_dataset
    from src.core.ops.judge_cache import JudgeCache

    posts = []
    result = {"is_high_quality": True, "failure_reason": None, "score": 0.97}

    def fake_post(url, json, timeout):
        posts.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse({"ok": True, "model": "qwen2.5:7b", "result": result})

    monkeypatch.setattr(sanitize_dataset.requests, "post", fake_post)

    checker = sanitize_dataset.LLMSanityChecker(
        model="qwen2.5:7b",
        inference_server_url="http://127.0.0.1:8765",
        cache=JudgeCache(tmp_path / "judge-cache.sqlite3"),
    )

    assert checker.check(_example(), {"npc_key": "chef_assistant"}) == result
    assert posts[0]["url"] == "http://127.0.0.1:8765/judge"
    assert posts[0]["json"]["model"] == "qwen2.5:7b"
    assert posts[0]["json"]["input"] == "How do I know chicken is safe?"
    assert (
        posts[0]["json"]["actual_output"] == "Cook chicken until the thickest part reaches 165°F."
    )
    assert posts[0]["json"]["context"] == ["No context provided."]
    assert "Classify the quality" in posts[0]["json"]["rubric"]


def test_llm_sanity_checker_inference_endpoint_result_is_cached(tmp_path, monkeypatch):
    from src.core.dataset import sanitize_dataset
    from src.core.ops.judge_cache import JudgeCache

    calls = {"count": 0}
    result = {"is_high_quality": True, "failure_reason": None, "score": 0.88}

    def fake_post(url, json, timeout):
        calls["count"] += 1
        return _FakeResponse({"ok": True, "result": result})

    monkeypatch.setattr(sanitize_dataset.requests, "post", fake_post)
    cache = JudgeCache(tmp_path / "judge-cache.sqlite3")
    checker = sanitize_dataset.LLMSanityChecker(
        model="qwen2.5:7b",
        inference_server_url="http://127.0.0.1:8765/",
        cache=cache,
    )

    assert checker.check(_example(), {"npc_key": "chef_assistant"}) == result
    assert checker.check(_example(), {"npc_key": "chef_assistant"}) == result
    assert calls["count"] == 1
    assert cache.stats()["entries"] == 1
    assert cache.stats()["total_hits"] == 1
