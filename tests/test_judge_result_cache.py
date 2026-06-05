from __future__ import annotations


def test_judge_cache_key_is_stable_and_content_sensitive(tmp_path):
    from src.core.ops.judge_cache import JudgeCache, JudgeCacheInput

    cache = JudgeCache(tmp_path / "judge.sqlite3")
    base = JudgeCacheInput(
        row_input="How do I dice onions?",
        row_output="Use a claw grip and sharp knife.",
        reference_context="Knife safety reference v1",
        rubric="culinary specificity rubric",
        judge_provider="ollama",
        judge_model="qwen2.5:7b",
    )
    same = JudgeCacheInput(
        row_input="How do I dice onions?",
        row_output="Use a claw grip and sharp knife.",
        reference_context="Knife safety reference v1",
        rubric="culinary specificity rubric",
        judge_provider="ollama",
        judge_model="qwen2.5:7b",
    )
    changed = JudgeCacheInput(
        row_input="How do I dice onions?",
        row_output="Use a claw grip.",
        reference_context="Knife safety reference v1",
        rubric="culinary specificity rubric",
        judge_provider="ollama",
        judge_model="qwen2.5:7b",
    )

    assert cache.make_key(base) == cache.make_key(same)
    assert cache.make_key(base) != cache.make_key(changed)


def test_judge_cache_round_trips_result_without_llm_call(tmp_path):
    from src.core.ops.judge_cache import JudgeCache, JudgeCacheInput

    cache = JudgeCache(tmp_path / "judge.sqlite3")
    item = JudgeCacheInput(
        row_input={"messages": [{"role": "user", "content": "Fact?"}]},
        row_output={"content": "Grounded answer."},
        reference_context=["source A", "source B"],
        rubric={"min_score": 7},
        judge_provider="ollama",
        judge_model="llama3.1:latest",
    )

    assert cache.get(item) is None
    written = cache.put(
        item,
        result={"score": 8.5, "label": "pass", "reasoning": "grounded"},
        latency_ms=123,
    )
    cached = cache.get(item)

    assert cached is not None
    assert cached["cache_key"] == written["cache_key"]
    assert cached["result"]["score"] == 8.5
    assert cached["result"]["label"] == "pass"
    assert cached["hit_count"] == 1

    cached_again = cache.get(item)
    assert cached_again["hit_count"] == 2


def test_judge_cache_stats_reports_entries_and_hits(tmp_path):
    from src.core.ops.judge_cache import JudgeCache, JudgeCacheInput

    cache = JudgeCache(tmp_path / "judge.sqlite3")
    item = JudgeCacheInput(
        row_input="q",
        row_output="a",
        reference_context="ctx",
        rubric="rubric",
        judge_provider="ollama",
        judge_model="qwen2.5:7b",
    )
    cache.put(item, result={"score": 9})
    cache.get(item)
    stats = cache.stats()

    assert stats["entries"] == 1
    assert stats["total_hits"] == 1
    assert stats["by_judge"] == {"ollama/qwen2.5:7b": 1}
