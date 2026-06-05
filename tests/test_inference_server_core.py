from __future__ import annotations

import json


class FakeOllamaClient:
    def __init__(self):
        self.chat_calls = []
        self.stopped = []

    def status(self):
        return {"ok": True, "models": ["qwen2.5:7b"], "running_models": ["qwen2.5:7b"]}

    def chat(self, *, model, messages, format=None, options=None, keep_alive=None, timeout=None):
        self.chat_calls.append(
            {
                "model": model,
                "messages": messages,
                "format": format,
                "options": options,
                "keep_alive": keep_alive,
                "timeout": timeout,
            }
        )
        if format == "json":
            return {"message": {"content": json.dumps({"is_high_quality": True, "score": 0.91, "failure_reason": None})}}
        return {"message": {"content": "ok"}}

    def unload(self, model=None):
        self.stopped.append(model)
        return [model or "qwen2.5:7b"]


def test_inference_service_status_returns_backend_and_running_models():
    from src.core.ops.inference_server import InferenceService

    service = InferenceService(client=FakeOllamaClient(), default_model="qwen2.5:7b")

    result = service.status()

    assert result["ok"] is True
    assert result["backend"] == "ollama"
    assert result["default_model"] == "qwen2.5:7b"
    assert result["models"] == ["qwen2.5:7b"]
    assert result["running_models"] == ["qwen2.5:7b"]


def test_inference_service_warm_uses_small_nonstream_chat_call():
    from src.core.ops.inference_server import InferenceService

    client = FakeOllamaClient()
    service = InferenceService(client=client, default_model="qwen2.5:7b")

    result = service.warm({"keep_alive": "20m"})

    assert result["ok"] is True
    assert result["model"] == "qwen2.5:7b"
    assert client.chat_calls[0]["model"] == "qwen2.5:7b"
    assert client.chat_calls[0]["options"]["num_predict"] == 1
    assert client.chat_calls[0]["keep_alive"] == "20m"


def test_inference_service_judge_returns_parsed_json_and_contract_metadata():
    from src.core.ops.inference_server import InferenceService

    client = FakeOllamaClient()
    service = InferenceService(client=client, default_model="qwen2.5:7b")

    result = service.judge(
        {
            "input": "How hot should chicken be?",
            "actual_output": "165°F at the thickest part.",
            "context": ["Chicken must reach 165°F."],
        }
    )

    assert result["ok"] is True
    assert result["model"] == "qwen2.5:7b"
    assert result["result"] == {"is_high_quality": True, "score": 0.91, "failure_reason": None}
    call = client.chat_calls[0]
    assert call["format"] == "json"
    assert call["options"]["temperature"] == 0.1
    assert "How hot should chicken be?" in call["messages"][0]["content"]
    assert "165°F at the thickest part." in call["messages"][0]["content"]


def test_inference_service_unload_stops_requested_model():
    from src.core.ops.inference_server import InferenceService

    client = FakeOllamaClient()
    service = InferenceService(client=client, default_model="qwen2.5:7b")

    result = service.unload({"model": "qwen2.5:7b"})

    assert result == {"ok": True, "stopped_models": ["qwen2.5:7b"]}
    assert client.stopped == ["qwen2.5:7b"]
