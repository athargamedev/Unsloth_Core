from __future__ import annotations

import sys
from pathlib import Path

TEST_EVALS_ROOT = Path(__file__).resolve().parent / "evals"
if str(TEST_EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_EVALS_ROOT))


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_dataset_judge_can_route_through_inference_server(monkeypatch):
    import metrics
    from metrics import DatasetJudgeOllamaModel

    posts = []

    def fake_post(url, json, timeout):
        posts.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse({"ok": True, "message": {"content": "score ok"}})

    monkeypatch.setattr(metrics.requests, "post", fake_post)

    judge = DatasetJudgeOllamaModel(
        model="qwen2.5:7b",
        temperature=0.0,
        inference_server_url="http://127.0.0.1:8765/",
        think=False,
    )

    response, cost = judge.generate("score this")

    assert response == "score ok"
    assert cost == 0
    assert posts[0]["url"] == "http://127.0.0.1:8765/chat"
    assert posts[0]["json"]["model"] == "qwen2.5:7b"
    assert posts[0]["json"]["messages"] == [{"role": "user", "content": "score this"}]
    assert posts[0]["json"]["options"]["temperature"] == 0.0
