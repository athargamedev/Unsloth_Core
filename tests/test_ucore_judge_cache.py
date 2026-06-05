from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_ucore_judge_cache_stats_json_for_empty_cache(tmp_path):
    db = tmp_path / "judge.sqlite3"
    result = subprocess.run(
        [
            sys.executable,
            "./ucore",
            "judge-cache",
            "stats",
            "--db-path",
            str(db),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["entries"] == 0
    assert payload["total_hits"] == 0
    assert payload["by_judge"] == {}


def test_ucore_judge_cache_stats_table_for_empty_cache(tmp_path):
    db = tmp_path / "judge.sqlite3"
    result = subprocess.run(
        [
            sys.executable,
            "./ucore",
            "judge-cache",
            "stats",
            "--db-path",
            str(db),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    out = result.stdout.lower()
    assert "judge cache" in out
    assert "entries" in out
    assert "total_hits" in out
