from __future__ import annotations

import json


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


def test_llm_sanity_checker_uses_judge_cache_on_repeated_rows(tmp_path, monkeypatch):
    from src.core.dataset import sanitize_dataset
    from src.core.ops.judge_cache import JudgeCache

    calls = {"count": 0}
    judge_result = {"is_high_quality": True, "failure_reason": None, "score": 0.94}

    def fake_post(url, json, timeout):
        calls["count"] += 1
        return _FakeResponse({"message": {"content": __import__("json").dumps(judge_result)}})

    monkeypatch.setattr(sanitize_dataset.requests, "post", fake_post)

    cache = JudgeCache(tmp_path / "judge-cache.sqlite3")
    checker = sanitize_dataset.LLMSanityChecker(model="qwen2.5:7b", cache=cache)

    first = checker.check(_example(), {"npc_key": "chef_assistant"})
    second = checker.check(_example(), {"npc_key": "chef_assistant"})

    assert first == judge_result
    assert second == judge_result
    assert calls["count"] == 1
    assert cache.stats()["entries"] == 1
    assert cache.stats()["total_hits"] == 1


def test_llm_sanity_checker_cache_key_includes_reference_context(tmp_path, monkeypatch):
    from src.core.dataset import sanitize_dataset
    from src.core.ops.judge_cache import JudgeCache

    calls = {"count": 0}

    def fake_post(url, json, timeout):
        calls["count"] += 1
        result = {"is_high_quality": True, "failure_reason": None, "score": 0.8 + calls["count"] / 100}
        return _FakeResponse({"message": {"content": __import__("json").dumps(result)}})

    monkeypatch.setattr(sanitize_dataset.requests, "post", fake_post)

    ref = tmp_path / "ref.md"
    ref.write_text("Chicken must reach 165°F.", encoding="utf-8")
    cache = JudgeCache(tmp_path / "judge-cache.sqlite3")
    checker = sanitize_dataset.LLMSanityChecker(model="qwen2.5:7b", cache=cache)

    first = checker.check(_example(), {"npc_key": "chef_assistant", "reference_doc": str(ref)})
    ref.write_text("Chicken must reach 165°F and rest for carryover safety.", encoding="utf-8")
    second = checker.check(_example(), {"npc_key": "chef_assistant", "reference_doc": str(ref)})

    assert first != second
    assert calls["count"] == 2
    assert cache.stats()["entries"] == 2
