#!/usr/bin/env python3
"""
supabase_integration_check.py

Phase: Supabase integration reliability

Checks/bootstraps NPC profile alignment between subject specs and Supabase,
then runs a minimal dialogue memory probe through DB functions.

Usage:
    python scripts/ops/supabase_integration_check.py --npc-key chemistry_instructor
    python scripts/ops/supabase_integration_check.py --npc-key chemistry_instructor --player-id 11111111-1111-1111-1111-111111111111
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths


def load_spec(npc_key: str) -> dict:
    spec_path = paths.subjects_root() / f"{npc_key}.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"Subject spec not found: {spec_path}")
    with open(spec_path) as f:
        return json.load(f)


def latest_gguf(npc_key: str) -> str | None:
    export_dir = paths.export_dir(npc_key)
    if not export_dir.exists():
        return None
    ggufs = sorted(export_dir.glob("*.gguf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not ggufs:
        return None
    return str(ggufs[0])


def connect_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

    from supabase import create_client

    return create_client(url, key)


def upsert_profile(client, npc_key: str, spec: dict, model_path: str | None):
    npc_name = spec.get("npc_name") or npc_key
    description = spec.get("identity", "")

    metadata = {
        "source": "unsloth_core_phase_supabase_check",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "subject_file": f"{npc_key}.json",
    }

    payload = {
        "p_npc_id": npc_key,
        "p_npc_name": npc_name,
        "p_display_name": npc_name,
        "p_description": description,
        "p_lora_path": model_path or "",
        "p_lora_weight": 1.0,
        "p_metadata": metadata,
    }

    # Function returns npc_profiles row
    res = client.rpc("upsert_npc_profile", payload).execute()
    return res.data


def run_probe(client, npc_key: str, player_id: str):
    # 1) session open/get
    ses = client.rpc(
        "get_or_create_session",
        {
            "p_player_id": player_id,
            "p_npc_id": npc_key,
            "p_session_type": "dialogue",
        },
    ).execute()
    session_id = ses.data
    if not session_id:
        raise RuntimeError("get_or_create_session returned empty session id")

    # 2) write two turns
    t1 = client.rpc(
        "insert_turn_fast",
        {
            "p_session_id": session_id,
            "p_player_id": player_id,
            "p_npc_id": npc_key,
            "p_role": "player",
            "p_content": "Hello, this is a reliability probe turn from Unsloth_Core.",
            "p_tokens_used": 12,
            "p_latency_ms": 50,
        },
    ).execute()
    if not t1.data:
        raise RuntimeError("insert_turn_fast failed for player turn")

    t2 = client.rpc(
        "insert_turn_fast",
        {
            "p_session_id": session_id,
            "p_player_id": player_id,
            "p_npc_id": npc_key,
            "p_role": "npc",
            "p_content": "Probe acknowledged. Dialogue pipeline and memory path check in progress.",
            "p_tokens_used": 14,
            "p_latency_ms": 65,
        },
    ).execute()
    if not t2.data:
        raise RuntimeError("insert_turn_fast failed for npc turn")

    # 3) summarize and verify latest memory retrieval
    summary_text = "Probe session completed successfully; player greeted NPC and NPC responded."
    mem = client.rpc(
        "summarize_dialogue_session",
        {
            "p_session_id": session_id,
            "p_summary": summary_text,
            "p_importance": 0.25,
        },
    ).execute()

    mem_text = client.rpc(
        "get_player_npc_memory",
        {
            "p_player_id": player_id,
            "p_npc_id": npc_key,
        },
    ).execute()

    return {
        "session_id": session_id,
        "turn_ids": [t1.data, t2.data],
        "memory_id": mem.data,
        "memory_text": mem_text.data,
    }


def main():
    parser = argparse.ArgumentParser(description="Supabase compatibility and memory probe for an NPC")
    parser.add_argument("--npc-key", required=True, help="NPC key, e.g. chemistry_instructor")
    parser.add_argument(
        "--player-id",
        default="00000000-0000-0000-0000-000000000001",
        help="Probe player UUID",
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Only upsert/verify npc_profiles; skip dialogue/memory probe",
    )
    args = parser.parse_args()

    print("=" * 64)
    print(" Supabase Integration Check")
    print("=" * 64)
    print(f" NPC: {args.npc_key}")

    spec = load_spec(args.npc_key)
    model_path = latest_gguf(args.npc_key)
    print(f" Subject: {PROJECT_ROOT / 'subjects' / f'{args.npc_key}.json'}")
    print(f" Latest GGUF: {model_path or '[none found]'}")

    client = connect_supabase()

    print("\n[1/3] Upserting npc_profiles alignment...")
    profile = upsert_profile(client, args.npc_key, spec, model_path)
    print("  ✓ upsert_npc_profile OK")
    if profile:
        print(f"    npc_id={profile.get('npc_id')}")
        print(f"    display_name={profile.get('display_name')}")

    if args.skip_probe:
        print("\n[2/3] Probe skipped by flag --skip-probe")
        print("\nResult: PASS (profile alignment check)")
        return

    print("\n[2/3] Running dialogue + memory probe...")
    result = run_probe(client, args.npc_key, args.player_id)
    print("  ✓ get_or_create_session / insert_turn_fast / summarize_dialogue_session / get_player_npc_memory")
    print(f"    session_id={result['session_id']}")
    print(f"    memory_id={result['memory_id']}")
    print(f"    memory_text={result['memory_text']}")

    print("\n[3/3] Final verdict")
    if result.get("memory_text"):
        print("  PASS: Supabase runtime path is healthy for this NPC")
    else:
        print("  WARN: Probe wrote data but latest memory was empty")


if __name__ == "__main__":
    main()
