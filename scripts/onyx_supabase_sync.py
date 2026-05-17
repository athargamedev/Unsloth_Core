#!/usr/bin/env python3
"""Sync Supabase data into Onyx as searchable documents.

This script acts as a bridge connector between Supabase and Onyx:
  - Reads data from Supabase tables (test_results, npc_memories,
    dialogue_sessions, dialogue_turns, npc_profiles)
  - Pushes each row as a document into Onyx via the Ingestion API
  - Metadata includes source_type=supabase, table_name, and npc_key
    for filtered searches

Usage:
  # Sync all tables for all NPCs
  python3 scripts/onyx_supabase_sync.py

  # Sync only test_results for a specific NPC
  python3 scripts/onyx_supabase_sync.py --tables test_results --npc chemistry_instructor

  # Dry run (print what would be done without ingesting)
  python3 scripts/onyx_supabase_sync.py --dry-run
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure we can import from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.onyx_client import OnyxClient


# ---------------------------------------------------------------------------
# Supabase connection helpers
# ---------------------------------------------------------------------------

def _env_or_file(key: str, default: str = "") -> str:
    """Resolve from env, then .env file, then default."""
    # Check env
    val = os.environ.get(key)
    if val:
        return val
    # Check .env
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


def get_supabase_rest_url() -> str:
    """Get the Supabase REST API URL from env."""
    url = _env_or_file("SUPABASE_URL")
    if url:
        return url.rstrip("/") + "/rest/v1"
    # Fallback: try the local Supabase
    return "http://127.0.0.1:16437/rest/v1"  # local Supabase Kong API


def get_supabase_key() -> str:
    """Get the Supabase service role key or anon key."""
    key = _env_or_file("SUPABASE_SERVICE_ROLE_KEY") or _env_or_file("SUPABASE_ANON_KEY")
    if key:
        return key
    return ""  # local Supabase allows anon by default


def get_supabase_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    key = get_supabase_key()
    if key:
        headers["apikey"] = key
        headers["Authorization"] = f"Bearer {key}"
    return headers


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

TABLE_DEFINITIONS = {
    "test_results": {
        "id_field": "id",
        "text_fields": None,  # auto-detect (all except id/timestamps)
        "semantic_template": "Test Result: {npc_id} {test_name}",
        "description": "Smoke test and evaluation results per NPC",
    },
    "npc_memories": {
        "id_field": "id",
        "text_fields": ["npc_id", "memory_type", "content", "importance"],
        "semantic_template": "Memory: {npc_id} {memory_type}",
        "description": "NPC cross-session memories and summaries",
    },
    "dialogue_sessions": {
        "id_field": "id",
        "text_fields": ["npc_id", "status", "summary", "turn_count", "session_type"],
        "semantic_template": "Dialogue Session: {npc_id} ({status})",
        "description": "Dialogue session records with summaries",
    },
    "dialogue_turns": {
        "id_field": "id",
        "text_fields": ["npc_id", "role", "content", "tokens_used"],
        "semantic_template": "Dialogue Turn: {npc_id} {role}",
        "description": "Individual dialogue turns between player and NPC",
    },
    "npc_profiles": {
        "id_field": "npc_id",
        "text_fields": ["npc_id", "npc_name", "description", "system_prompt",
                        "domain_knowledge", "voice_rules"],
        "semantic_template": "NPC Profile: {npc_id}",
        "description": "NPC identity and knowledge specifications",
    },
}


def fetch_supabase_table(
    table_name: str,
    npc_key: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Fetch rows from a Supabase table via REST API.

    Args:
        table_name: Name of the Supabase table.
        npc_key: Optional NPC key filter (uses npc_id column).
        limit: Max rows to fetch.
    """
    import requests as req

    base_url = get_supabase_rest_url()
    headers = get_supabase_headers()
    url = f"{base_url}/{table_name}"

    params: dict[str, Any] = {"limit": limit}
    # Handle different timestamp column names per table
    time_col = "created_at"
    if table_name == "dialogue_sessions":
        time_col = "started_at"
    elif table_name == "dialogue_turns":
        time_col = "created_at"
    params["order"] = f"{time_col}.desc"
    if npc_key and table_name != "npc_profiles":
        # Most tables use npc_id column
        params["npc_id"] = f"eq.{npc_key}"
    elif npc_key and table_name == "npc_profiles":
        params["npc_id"] = f"eq.{npc_key}"

    try:
        resp = req.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
        if isinstance(rows, list):
            return rows
        return []
    except Exception as e:
        print(f"  [warn] Failed to fetch {table_name}: {e}")
        return []


def fetch_all_tables(
    npc_key: str | None = None,
    tables: list[str] | None = None,
    limit: int = 500,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch data from multiple Supabase tables.

    Returns:
        Dict mapping table_name -> list of rows.
    """
    import requests as req  # noqa: F401

    target_tables = tables or list(TABLE_DEFINITIONS.keys())
    result: dict[str, list[dict[str, Any]]] = {}

    for table_name in target_tables:
        if table_name not in TABLE_DEFINITIONS:
            print(f"  [warn] Unknown table: {table_name}, skipping")
            continue
        desc = TABLE_DEFINITIONS[table_name]["description"]
        print(f"  Fetching {table_name} ({desc})...", end=" ")
        rows = fetch_supabase_table(table_name, npc_key=npc_key, limit=limit)
        print(f"{len(rows)} rows")
        result[table_name] = rows

    return result


# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------

def run_sync(
    onyx: OnyxClient,
    npc_key: str | None = None,
    tables: list[str] | None = None,
    limit: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sync Supabase data into Onyx.

    Args:
        onyx: Configured OnyxClient instance.
        npc_key: If set, only sync data for this NPC.
        tables: If set, only sync these tables.
        limit: Max rows per table.
        dry_run: If True, print actions without executing.

    Returns:
        Summary dict with counts per table.
    """
    summary: dict[str, Any] = {"total_documents": 0, "per_table": {}}

    # Step 1: Fetch data from Supabase
    print(f"\n{'='*60}")
    print(f"Supabase → Onyx Sync")
    print(f"{'='*60}")
    if npc_key:
        print(f"NPC filter: {npc_key}")
    if dry_run:
        print("DRY RUN — no documents will be ingested")
    print()

    all_data = fetch_all_tables(npc_key=npc_key, tables=tables, limit=limit)

    # Step 2: Ingest each table's rows into Onyx
    total_ingested = 0
    for table_name, rows in all_data.items():
        if not rows:
            print(f"  No data for {table_name}, skipping")
            summary["per_table"][table_name] = 0
            continue

        table_def = TABLE_DEFINITIONS[table_name]
        id_field = table_def["id_field"]
        text_fields = table_def.get("text_fields")
        semantic_template = table_def["semantic_template"]

        if dry_run:
            print(f"\n  [{table_name}] Would ingest {len(rows)} documents:")
            for i, row in enumerate(rows[:3]):
                row_id = row.get(id_field, "?")
                npc = row.get("npc_id", npc_key or "?")
                print(f"    {i+1}. supabase-{table_name}-{row_id}-{npc}")
            if len(rows) > 3:
                print(f"    ... and {len(rows) - 3} more")
            summary["per_table"][table_name] = len(rows)
            total_ingested += len(rows)
            continue

        # Ingest via the client's batch helper
        results = onyx.ingest_supabase_table(
            npc_key=npc_key or "all",
            table_name=table_name,
            rows=rows,
            id_field=id_field,
            text_fields=text_fields,
            semantic_template=semantic_template,
        )

        success_count = sum(1 for r in results if "document_id" in r)
        print(f"\n  [{table_name}] Ingested {success_count}/{len(rows)} documents")
        summary["per_table"][table_name] = success_count
        total_ingested += success_count

    summary["total_documents"] = total_ingested

    # Step 3: Summary
    print(f"\n{'='*60}")
    if dry_run:
        print(f"DRY RUN: Would ingest {total_ingested} documents total")
    else:
        print(f"Sync complete: {total_ingested} documents ingested")
        print(f"Searchable in Onyx with: source_type=supabase, npc_key=<value>")
    print(f"{'='*60}")

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Supabase data into Onyx as searchable documents",
    )
    parser.add_argument(
        "--npc", type=str, default=None,
        help="NPC key to filter by (e.g., chemistry_instructor). Syncs all if omitted.",
    )
    parser.add_argument(
        "--tables", type=str, nargs="+",
        choices=list(TABLE_DEFINITIONS.keys()) + ["all"],
        default=["all"],
        help="Tables to sync (default: all)",
    )
    parser.add_argument(
        "--limit", type=int, default=500,
        help="Max rows per table (default: 500)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without actually ingesting",
    )
    parser.add_argument(
        "--onyx-url", type=str, default=None,
        help="Onyx base URL (default: auto-detect from env)",
    )

    args = parser.parse_args()
    tables = list(TABLE_DEFINITIONS.keys()) if "all" in (args.tables or ["all"]) else args.tables

    # Initialize Onyx client
    onyx = OnyxClient(base_url=args.onyx_url)
    if not onyx.health():
        print("Error: Onyx server is not reachable")
        sys.exit(1)
    print(f"Connected to Onyx ({onyx.get_version()})")

    # Run sync
    summary = run_sync(
        onyx=onyx,
        npc_key=args.npc,
        tables=tables,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    # Exit with code if nothing was done
    if summary["total_documents"] == 0 and all(v == 0 for v in summary["per_table"].values()):
        print("\nNothing to sync (all tables empty or unreachable)")
        sys.exit(0)


if __name__ == "__main__":
    main()
