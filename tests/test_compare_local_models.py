from src.core.ops.compare_local_models import compare_models


def test_compare_models_scores_and_sorts(monkeypatch):
    class Dummy:
        pass
    def fake_benchmark(host, model, prompt, system_prompt=None):
        from src.core.ops.benchmark_ollama import ChatBenchmarkResult
        if model == "a":
            return ChatBenchmarkResult(model, prompt, 100.0, 10, 20.0, 5, 10.0, 5.0)
        return ChatBenchmarkResult(model, prompt, 10.0, 20, 5.0, 10, 2.5, 20.0)
    monkeypatch.setattr("src.core.ops.compare_local_models.benchmark_chat", fake_benchmark)
    results = compare_models("http://localhost:11434", ["a", "b"], ["p1", "p2"])
    assert results[0].model == "b"
    assert results[0].score > results[1].score
