#!/usr/bin/env python3
"""Index selected Unsloth_Core repository context into local Onyx.

This uses Onyx's ingestion API, not a heavyweight connector, so it is safe for
local resource-constrained workflows. It intentionally indexes docs/specs/key
workflow scripts rather than the whole repo, avoiding venvs, generated datasets,
frontend runtime blobs, and model artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOBS = [
    "README.md",
    "AGENTS.md",
    "ucore",
    "docs/**/*.md",
    "subjects/*.json",
    "configs/**/*.yaml",
    "scripts/generate_dataset.py",
    "scripts/onyx_client.py",
    "scripts/onyx_index_repo.py",
    "scripts/sanitize_dataset.py",
    "scripts/train.py",
    "scripts/export.py",
    "scripts/export_adapter.py",
    "scripts/smoke_test.py",
    "scripts/evaluate.py",
    "scripts/compare_runs.py",
    "scripts/plan_execution.py",
    "scripts/plan_batch_execution.py",
    "scripts/validate_config.py",
    "scripts/validate_subject_spec.py",
    "_config/paths.py",
]
SKIP_PARTS = {
    ".git",
    ".hermes",
    ".pytest_cache",
    "unsloth_env",
    "node_modules",
    "datasets",
    "outputs",
    "exports",
    "eval",
    "wandb",
    "onyx_data",
    ".runtime",
}


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def iter_files(globs: Iterable[str], max_bytes: int) -> list[Path]:
    files: dict[Path, None] = {}
    for pattern in globs:
        for path in PROJECT_ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(PROJECT_ROOT)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            if path.stat().st_size > max_bytes:
                continue
            files[path] = None
    return sorted(files, key=lambda p: str(p.relative_to(PROJECT_ROOT)))


def document_id_for(rel_path: str) -> str:
    digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:16]
    return f"unsloth_core:{digest}"


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def section_for(rel_path: str, text: str) -> dict:
    heading = rel_path
    body = f"Repository path: {rel_path}\n\n{text}"
    return {"type": "text", "text": body, "link": f"file://{PROJECT_ROOT / rel_path}", "heading": heading}


def upsert_document(session: requests.Session, base_url: str, headers: dict[str, str], path: Path, timeout: int) -> dict:
    rel_path = str(path.relative_to(PROJECT_ROOT))
    text = read_text(path)
    if not text or not text.strip():
        return {"path": rel_path, "skipped": "empty_or_binary"}
    doc_id = document_id_for(rel_path)
    suffix = path.suffix.lower().lstrip(".") or "script"
    payload = {
        "document": {
            "id": doc_id,
            "sections": [section_for(rel_path, text)],
            "source": "ingestion_api",
            "semantic_identifier": rel_path,
            "metadata": {
                "project": "Unsloth_Core",
                "repo_path": rel_path,
                "kind": suffix,
                "index_profile": "local_repo_context",
            },
            "title": rel_path,
            "from_ingestion_api": True,
        }
    }
    response = session.post(f"{base_url}/api/onyx-api/ingestion", headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return {"path": rel_path, "document_id": data.get("document_id", doc_id), "already_existed": data.get("already_existed")}


def cancel_secondary_index(session: requests.Session, base_url: str, headers: dict[str, str], timeout: int) -> None:
    response = session.post(f"{base_url}/api/search-settings/cancel-new-embedding", headers=headers, json={}, timeout=timeout)
    response.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Index selected Unsloth_Core repo files into local Onyx")
    parser.add_argument("--glob", action="append", dest="globs", help="Repo-relative glob to index; repeatable. Defaults to docs/specs/key scripts.")
    parser.add_argument("--max-file-kb", type=int, default=256, help="Skip files larger than this (default: 256 KB)")
    parser.add_argument("--limit", type=int, default=0, help="Index at most N files (default: all selected)")
    parser.add_argument("--sleep", type=float, default=0.15, help="Seconds between ingestion calls (default: 0.15)")
    parser.add_argument("--timeout", type=int, default=90, help="Per-request timeout seconds (default: 90)")
    parser.add_argument("--no-cancel-secondary", action="store_true", help="Do not cancel Onyx secondary embedding/contextual-RAG index first")
    parser.add_argument("--dry-run", action="store_true", help="Print files that would be indexed without writing to Onyx")
    args = parser.parse_args()

    env = load_env()
    base_url = (env.get("ONYX_BASE_URL") or "http://localhost").rstrip("/")
    api_key = env.get("ONYX_API_KEY")
    if not api_key:
        print("Error: ONYX_API_KEY is required. Put it in .env or export it.", file=sys.stderr)
        return 2

    files = iter_files(args.globs or DEFAULT_GLOBS, max_bytes=args.max_file_kb * 1024)
    if args.limit:
        files = files[: args.limit]
    print(f"Selected {len(files)} files for Onyx indexing")
    for path in files[:20]:
        print(f"  - {path.relative_to(PROJECT_ROOT)}")
    if len(files) > 20:
        print(f"  ... {len(files) - 20} more")
    if args.dry_run:
        return 0

    session = requests.Session()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if not args.no_cancel_secondary:
        cancel_secondary_index(session, base_url, headers, args.timeout)
        print("Cancelled secondary embedding/index build to avoid contextual-RAG local LLM failures")

    ok = 0
    failed = 0
    for idx, path in enumerate(files, start=1):
        rel = path.relative_to(PROJECT_ROOT)
        try:
            result = upsert_document(session, base_url, headers, path, args.timeout)
            ok += 1
            print(f"[{idx}/{len(files)}] indexed {rel} -> {result['document_id']}")
        except Exception as exc:
            failed += 1
            print(f"[{idx}/{len(files)}] FAILED {rel}: {exc}", file=sys.stderr)
        if args.sleep:
            time.sleep(args.sleep)

    print(json.dumps({"indexed": ok, "failed": failed, "selected": len(files)}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
