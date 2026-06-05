from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.pipeline_db import PipelineDB


class _FakeCursor:
    def __init__(self) -> None:
        self.query = None
        self.params = None
        self.closed = False

    def execute(self, query, params):
        self.query = query
        self.params = list(params)

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    def cursor(self):
        return self.cursor_obj


def test_direct_create_eval_session_serializes_json_metadata(monkeypatch):
    db = PipelineDB.__new__(PipelineDB)
    db._mode = "direct"
    db._conn = _FakeConn()

    monkeypatch.setattr(db, "_ensure_direct_connected", lambda: None)
    monkeypatch.setattr(db, "_row_to_dict", lambda cur: [{"id": "session-1"}])

    result = db._direct_create_eval_session(
        "session-1",
        "history_guide",
        "2026-05-21T00:00:00Z",
        {
            "metadata": {"html": True, "track": False},
            "judge_model": "qwen3:latest",
        },
    )

    assert result == {"id": "session-1"}
    assert isinstance(db._conn.cursor_obj.params[3], str)
    assert db._conn.cursor_obj.params[3] == '{"html": true, "track": false}'
    assert db._conn.cursor_obj.closed is True
