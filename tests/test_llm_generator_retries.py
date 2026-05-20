import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.dataset.generate_dataset as gd


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

    def post(self, url, json, headers, timeout):
        step = self.steps[self.calls]
        self.calls += 1
        if isinstance(step, Exception):
            raise step
        return step


def test_openai_generator_retries_connection_error_then_succeeds(monkeypatch):
    generator = gd.OpenAIGenerator(model="gpt-test", api_key="test-key")
    calls = []
    sleeps = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if len(calls) == 1:
            raise gd.requests.exceptions.ConnectionError("boom")
        return DummyResponse({"choices": [{"message": {"content": "  openai ok  "}}]})

    monkeypatch.setattr(gd.requests, "post", fake_post)
    monkeypatch.setattr(gd.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = generator.generate("system", "user", json_format=True)

    assert result == "openai ok"
    assert len(calls) == 2
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}
    assert sleeps == [1]


def test_anthropic_generator_retries_connection_error_then_succeeds(monkeypatch):
    generator = gd.AnthropicGenerator(model="claude-test", api_key="test-key")
    calls = []
    sleeps = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if len(calls) == 1:
            raise gd.requests.exceptions.ConnectionError("boom")
        return DummyResponse({"content": [{"text": "  anthropic ok  "}]})

    monkeypatch.setattr(gd.requests, "post", fake_post)
    monkeypatch.setattr(gd.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = generator.generate("system", "user", json_format=False)

    assert result == "anthropic ok"
    assert len(calls) == 2
    assert sleeps == [1]


def test_openai_generator_async_retries_timeout_then_succeeds(monkeypatch):
    if gd.aiohttp is None:
        return

    generator = gd.OpenAIGenerator(model="gpt-test", api_key="test-key")
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(gd.asyncio, "sleep", fake_sleep)

    session = AsyncDummySession([
        asyncio.TimeoutError(),
        AsyncDummyResponse({"choices": [{"message": {"content": "done"}}]}),
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
    assert sleeps == [1]
