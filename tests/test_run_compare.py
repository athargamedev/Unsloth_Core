from src.core.ops.run_compare import compare_runs, write_comparison_report


def test_compare_runs_prefers_higher_score(tmp_path):
    base = tmp_path / "run_a" / "artifacts.json"
    cand = tmp_path / "run_b" / "artifacts.json"
    base.parent.mkdir(parents=True)
    cand.parent.mkdir(parents=True)
    base.write_text(
        '{"run_id": "run_a", "metrics": {"pass_rate": 0.4, "passed": 4, "discarded": 1}}\n',
        encoding="utf-8",
    )
    cand.write_text(
        '{"run_id": "run_b", "metrics": {"pass_rate": 0.8, "passed": 8, "discarded": 0}}\n',
        encoding="utf-8",
    )
    comparison = compare_runs(base, cand)
    assert comparison.winner == "candidate"
    assert comparison.metrics_delta["delta"] > 0
    out = write_comparison_report(comparison, tmp_path / "comparison.json")
    assert out.exists()
