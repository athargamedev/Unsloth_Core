from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _FakeResponse:
    def __init__(self, grounded: bool = True, reason: str = ""):
        self.grounded = grounded
        self.reason = reason

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": f'{{"is_grounded": {str(self.grounded).lower()}, "reason": "{self.reason}"}}'
            }
        }


def test_generation_grounding_verifier_reuses_local_judge_cache(tmp_path, monkeypatch):
    from src.core.dataset._generate_shared import LLMGroundingVerifier

    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return _FakeResponse(True, "cached")

    monkeypatch.setenv("UCORE_JUDGE_CACHE_PATH", str(tmp_path / "judge-cache.sqlite3"))
    monkeypatch.setattr("src.core.dataset._generate_shared.requests.post", fake_post)

    verifier = LLMGroundingVerifier(model="qwen2.5:7b")
    first = verifier.verify("A grounded answer", ["Reference context"])
    second = verifier.verify("A grounded answer", ["Reference context"])

    assert first == second == (True, "cached")
    assert calls["count"] == 1


def test_generation_grounding_cache_key_uses_prompt_version_not_deepeval_entries(
    tmp_path, monkeypatch
):
    from src.core.dataset._generate_shared import LLMGroundingVerifier
    from src.core.ops.judge_cache import JudgeCache, JudgeCacheInput

    cache_path = tmp_path / "judge-cache.sqlite3"
    JudgeCache(cache_path).put(
        JudgeCacheInput(
            row_input="A grounded answer",
            row_output="Reference context",
            reference_context="Reference context",
            rubric={"task": "generation_grounding"},
            judge_provider="ollama",
            judge_model="qwen2.5:7b",
            prompt_version="deepeval-local-judge-v1",
        ),
        result={"is_grounded": False, "reason": "wrong cache family"},
    )
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return _FakeResponse(True, "fresh generation grounding")

    monkeypatch.setenv("UCORE_JUDGE_CACHE_PATH", str(cache_path))
    monkeypatch.setattr("src.core.dataset._generate_shared.requests.post", fake_post)

    verifier = LLMGroundingVerifier(model="qwen2.5:7b")
    assert verifier.verify("A grounded answer", ["Reference context"]) == (
        True,
        "fresh generation grounding",
    )
    assert calls["count"] == 1


def test_grounding_prompt_treats_forbidden_items_as_intents(tmp_path, monkeypatch):
    from src.core.dataset._generate_shared import LLMGroundingVerifier

    captured = {}

    def fake_post(_url, json, timeout):
        captured["prompt"] = json["messages"][0]["content"]
        return _FakeResponse(True, "grounded")

    monkeypatch.setenv("UCORE_JUDGE_CACHE_PATH", str(tmp_path / "judge-cache.sqlite3"))
    monkeypatch.setattr("src.core.dataset._generate_shared.requests.post", fake_post)

    verifier = LLMGroundingVerifier(model="qwen2.5:7b")
    result = verifier.verify(
        "Add a spoonful of sour cream to smooth the sauce.",
        ["Dairy can add fat and smoothness to a sauce."],
        spec={
            "guardrails": {
                "domain": {
                    "allowed": ["ingredient science"],
                    "forbidden": ["weight-loss recommendations"],
                }
            }
        },
    )

    assert result == (True, "grounded")
    assert "prohibited request intents" in captured["prompt"]
    assert "Ordinary ingredients" in captured["prompt"]
