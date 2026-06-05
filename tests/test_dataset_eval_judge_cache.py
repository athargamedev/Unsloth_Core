from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def test_dataset_eval_cli_exposes_local_judge_cache_flags(monkeypatch, tmp_path):
    from scripts.dataset import dataset_eval

    cache_path = tmp_path / "judge-cache.sqlite3"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dataset_eval.py",
            "data/npcs/specs/chef_assistant.json",
            "--technique",
            "ollama",
            "--judge-cache-path",
            str(cache_path),
            "--no-local-judge-cache",
        ],
    )

    args = dataset_eval.parse_args()

    assert args.judge_cache_path == str(cache_path)
    assert args.local_judge_cache is False


def test_dataset_eval_judge_cache_env_propagates_path_and_disable_flag(tmp_path):
    from scripts.dataset.dataset_eval import dataset_eval_judge_cache_env

    cache_path = tmp_path / "judge-cache.sqlite3"

    enabled_env = dataset_eval_judge_cache_env(cache_path, local_judge_cache=True)
    disabled_env = dataset_eval_judge_cache_env(cache_path, local_judge_cache=False)

    assert enabled_env["UCORE_JUDGE_CACHE_PATH"] == str(cache_path)
    assert "UCORE_JUDGE_CACHE_DISABLE" not in enabled_env
    assert disabled_env["UCORE_JUDGE_CACHE_PATH"] == str(cache_path)
    assert disabled_env["UCORE_JUDGE_CACHE_DISABLE"] == "1"


def test_dataset_judge_ollama_model_uses_local_cache_for_repeated_prompt(tmp_path, monkeypatch):
    import importlib.util

    metrics_path = PROJECT_ROOT / "tests" / "evals" / "metrics.py"
    spec = importlib.util.spec_from_file_location("dataset_eval_metrics", metrics_path)
    assert spec and spec.loader
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    DatasetJudgeOllamaModel = metrics.DatasetJudgeOllamaModel

    calls = {"count": 0}

    class _Message:
        content = '{"verdict": "ok"}'

    class _Response:
        message = _Message()

    class _FakeOllama:
        def chat(self, **kwargs):
            calls["count"] += 1
            return _Response()

    monkeypatch.setenv("UCORE_JUDGE_CACHE_PATH", str(tmp_path / "judge-cache.sqlite3"))
    model = DatasetJudgeOllamaModel(model="qwen2.5:7b", base_url="http://localhost:11434")
    monkeypatch.setattr(model, "load_model", lambda *args, **kwargs: _FakeOllama())

    first, _ = model.generate("same metric prompt")
    second, _ = model.generate("same metric prompt")

    assert first == second == '{"verdict": "ok"}'
    assert calls["count"] == 1
