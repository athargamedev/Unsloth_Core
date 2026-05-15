#!/usr/bin/env python3
"""Workflow Assistant Onyx helper.

Query the local Onyx index and print a concise, source-grounded context bundle.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.onyx_client import OnyxClient


def build_context(results: list[dict[str, object]], max_chars: int = 1800) -> str:
    lines: list[str] = []
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or f"source-{idx}"
        document_id = item.get("document_id") or f"source-{idx}"
        content = str(item.get("content") or "")
        if len(content) > max_chars:
            content = content[: max_chars - 3].rstrip() + "..."
        lines.append(f"Source {idx}: {title} ({document_id})\n{content}")
    return "\n\n".join(lines)


def query_onyx(query: str, base_url: str | None = None, api_key: str | None = None, max_results: int = 4) -> dict[str, object]:
    client = OnyxClient(base_url=base_url, api_key=api_key)
    results = client.search(query, max_results=max_results)
    return {
        "query": query,
        "results": results,
        "context": build_context(results),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query local Onyx for Workflow Assistant context.")
    parser.add_argument("query", help="User workflow question or topic to search in Onyx.")
    parser.add_argument("--onyx-url", default=None, help="Local Onyx base URL (default reads ONYX_BASE_URL or http://localhost)")
    parser.add_argument("--onyx-api-key", default=None, help="Optional Onyx bearer token")
    parser.add_argument("--max-results", type=int, default=4, help="Top-k results to return")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = query_onyx(args.query, base_url=args.onyx_url, api_key=args.onyx_api_key, max_results=args.max_results)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
