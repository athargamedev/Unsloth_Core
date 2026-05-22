import sys
from pathlib import Path
from types import SimpleNamespace

TEST_EVALS_ROOT = Path(__file__).resolve().parent / "evals"
sys.path.insert(0, str(TEST_EVALS_ROOT))

from metrics import DatasetJudgeOllamaModel


class FakeOllamaClient:
    def __init__(self):
        self.chat_kwargs = None

    def chat(self, **kwargs):
        self.chat_kwargs = kwargs
        return SimpleNamespace(message=SimpleNamespace(content="ok"))


def test_dataset_judge_disables_ollama_thinking_in_chat_calls(monkeypatch):
    judge = DatasetJudgeOllamaModel(model="qwen3:latest", think=False)
    client = FakeOllamaClient()
    monkeypatch.setattr(judge, "load_model", lambda async_mode=False: client)

    response, cost = judge.generate("score this")

    assert response == "ok"
    assert cost == 0
    assert client.chat_kwargs["think"] is False
