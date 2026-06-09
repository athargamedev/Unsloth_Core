#!/usr/bin/env python3
"""Durable judge-result cache for expensive LLM evaluation calls.

Cache key = hash(row input + row output + reference context + rubric + judge).
If the evaluated content and rubric are unchanged, callers can return the stored
judge result without paying Ollama/W&B/Confident latency again.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.paths import pipeline_root

DEFAULT_JUDGE_CACHE = pipeline_root() / "judge_cache.sqlite3"
SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize(value: Any) -> Any:
    """Return a deterministic JSON-compatible representation."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _normalize(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(
        _normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )


@dataclass(frozen=True)
class JudgeCacheInput:
    row_input: Any
    row_output: Any
    reference_context: Any
    rubric: Any
    judge_provider: str
    judge_model: str
    prompt_version: str = "judge-cache-v1"

    def payload(self) -> dict[str, Any]:
        return asdict(self)


class JudgeCache:
    """SQLite-backed cache for row-level judge outputs."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_JUDGE_CACHE)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def make_key(self, item: JudgeCacheInput) -> str:
        blob = _json({"schema_version": SCHEMA_VERSION, **item.payload()}).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def get(self, item: JudgeCacheInput) -> dict[str, Any] | None:
        key = self.make_key(item)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT cache_key, judge_provider, judge_model, prompt_version, result_json,
                       latency_ms, hit_count, created_at, updated_at
                FROM judge_results
                WHERE cache_key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                """
                UPDATE judge_results
                SET hit_count = hit_count + 1, updated_at = ?
                WHERE cache_key = ?
                """,
                (_utc_now(), key),
            )
            conn.commit()

        result = dict(row)
        result["result"] = json.loads(result.pop("result_json"))
        result["hit_count"] += 1
        return result

    def put(
        self, item: JudgeCacheInput, *, result: dict[str, Any], latency_ms: int | None = None
    ) -> dict[str, Any]:
        key = self.make_key(item)
        now = _utc_now()
        payload_json = _json(item.payload())
        result_json = _json(result)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO judge_results (
                    cache_key, schema_version, judge_provider, judge_model, prompt_version,
                    payload_json, result_json, latency_ms, hit_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    result_json = excluded.result_json,
                    latency_ms = excluded.latency_ms,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    SCHEMA_VERSION,
                    item.judge_provider,
                    item.judge_model,
                    item.prompt_version,
                    payload_json,
                    result_json,
                    latency_ms,
                    now,
                    now,
                ),
            )
            conn.commit()
        return {
            "cache_key": key,
            "judge_provider": item.judge_provider,
            "judge_model": item.judge_model,
            "prompt_version": item.prompt_version,
            "result": _normalize(result),
            "latency_ms": latency_ms,
            "hit_count": 0,
        }

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS entries, COALESCE(SUM(hit_count), 0) AS total_hits FROM judge_results"
            ).fetchone()
            by_judge_rows = conn.execute(
                """
                SELECT judge_provider, judge_model, COUNT(*) AS n
                FROM judge_results
                GROUP BY judge_provider, judge_model
                ORDER BY judge_provider, judge_model
                """
            ).fetchall()
        return {
            "db_path": str(self.db_path),
            "entries": int(row["entries"]),
            "total_hits": int(row["total_hits"]),
            "by_judge": {
                f"{r['judge_provider']}/{r['judge_model']}": int(r["n"]) for r in by_judge_rows
            },
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS judge_results (
                    cache_key TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    judge_provider TEXT NOT NULL,
                    judge_model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    latency_ms INTEGER,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_judge_results_judge ON judge_results(judge_provider, judge_model)"
            )
            conn.commit()
