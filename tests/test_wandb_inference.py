from __future__ import annotations

from scripts.ops.wandb_inference import (
    WandbInferenceClient,
    extract_json_object,
    wandb_inference_project,
)


def test_extract_json_object_from_model_text():
    assert extract_json_object('```json\n{"winner":"A"}\n```') == {"winner": "A"}


def test_wandb_inference_client_posts_openai_project(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setenv("WANDB_API_KEY", "test-key")
    monkeypatch.setattr("scripts.ops.wandb_inference.requests.post", fake_post)

    client = WandbInferenceClient(
        model="meta-llama/Llama-3.1-8B-Instruct", entity="team", project="proj"
    )
    assert client.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["OpenAI-Project"] == "team/proj"
    assert captured["json"]["model"] == "meta-llama/Llama-3.1-8B-Instruct"


def test_wandb_inference_project_defaults(monkeypatch):
    monkeypatch.setenv("WANDB_ENTITY", "entity-a")
    monkeypatch.setenv("WANDB_PROJECT", "project-a")
    assert wandb_inference_project() == "entity-a/project-a"
