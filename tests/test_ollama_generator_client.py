import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.dataset.generate_dataset_ollama as gdo


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class AsyncDummyResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    async def json(self):
        return self.payload


class AsyncDummySession:
    def __init__(self, steps):
        self.steps = steps
        self.calls = 0

    def post(self, url, json, timeout):
        step = self.steps[self.calls]
        self.calls += 1
        if isinstance(step, Exception):
            raise step
        return step


def test_ollama_generator_retries_connection_error_then_succeeds(monkeypatch):
    generator = gdo.OllamaGeneratorV2(model="test-model", url="http://localhost:11434/api/chat", max_retries=3)
    calls = []
    sleeps = []

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if len(calls) == 1:
            raise gdo.requests.exceptions.ConnectionError("boom")
        return DummyResponse({"message": {"content": "  ok  "}})

    monkeypatch.setattr(gdo.requests, "post", fake_post)
    monkeypatch.setattr(gdo.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = generator.generate("system", "user", json_format=True)

    assert result == "ok"
    assert len(calls) == 2
    assert calls[0]["json"]["format"] == "json"
    assert sleeps == [2.0]


def test_ollama_generator_async_retries_timeout_then_succeeds(monkeypatch):
    if gdo.aiohttp is None:
        return

    generator = gdo.OllamaGeneratorV2(model="test-model", url="http://localhost:11434/api/chat", max_retries=3)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(gdo.asyncio, "sleep", fake_sleep)

    session = AsyncDummySession([
        asyncio.TimeoutError(),
        AsyncDummyResponse({"message": {"content": "done"}}),
    ])

    result = asyncio.run(
        generator.generate_async(
            "system",
            "user",
            json_format=True,
            session=session,
        )
    )

    assert result == "done"
    assert session.calls == 2
    assert sleeps == [2.0]
