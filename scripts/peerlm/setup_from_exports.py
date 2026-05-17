#!/usr/bin/env python3
"""Create PeerLM resources from local peerlm/*_eval.json exports.

Uses PeerLM's authenticated Next.js server-action endpoints. Credentials are read
from environment variables; do not hardcode secrets in this file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP = "https://app.peerlm.com"
WORKSPACE = "ws-xpl4Bhc7"

ACTIONS = {
    "create_system_prompt": "609fcedc6fdfb26aba3f7d677b59de53eb6ded4273",
    "create_test_prompt": "6061f007d3f6330bb7e5d2e2b612c635b3f0387659",
    "create_suite": "604ca5d1772e7683e2d4162f7999692787d522f41b",
}

GENERATOR_MODELS = [
    "meta-llama/llama-3.2-3b-instruct",
    "qwen/qwen3-30b-a3b",
    "deepseek/deepseek-chat",
]
EVALUATOR_MODELS = ["google/gemini-2.5-flash"]


def login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{APP}/api/auth/sign-in/email",
        json={"email": email, "password": password},
        headers={"accept": "application/json", "content-type": "application/json"},
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"PeerLM login failed: HTTP {r.status_code} {r.text[:200]}")
    sr = s.get(f"{APP}/api/auth/get-session", timeout=20)
    if sr.status_code >= 400 or '"session"' not in sr.text:
        raise RuntimeError(f"PeerLM session check failed: HTTP {sr.status_code}")
    return s


def server_action(session: requests.Session, path: str, action_id: str, args: list) -> str:
    r = session.post(
        f"{APP}{path}",
        data=json.dumps(args),
        headers={
            "accept": "text/x-component",
            "content-type": "text/plain;charset=UTF-8",
            "next-action": action_id,
            "origin": APP,
            "referer": f"{APP}{path}",
        },
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Server action failed {path}: HTTP {r.status_code} {r.text[:500]}")
    return r.text


def extract_id(rsc_text: str, unique_value: str) -> str:
    idx = rsc_text.find(unique_value)
    if idx == -1:
        # Fall back to first UUID-like id in a returned object.
        m = re.search(r'"id":"([0-9a-f-]{36})"', rsc_text)
        if m:
            return m.group(1)
        raise RuntimeError(f"Could not find created object in response for {unique_value!r}")
    window = rsc_text[max(0, idx - 2000): idx + 2000]
    matches = list(re.finditer(r'"id":"([0-9a-f-]{36})"', window))
    if not matches:
        raise RuntimeError(f"Could not extract id near {unique_value!r}")
    return matches[-1].group(1)


def load_export(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_questions(export: dict) -> list[dict]:
    rows = []
    for persona in export.get("personas", []):
        pname = persona.get("persona_name", "General")
        category = pname.split("—")[-1].strip().split("&")[0].strip().lower().replace(" ", "_")
        for idx, question in enumerate(persona.get("test_questions", []), start=1):
            rows.append({"category": category, "question": question, "persona_name": pname, "index": idx})
    return rows


def create_for_export(session: requests.Session, export_path: Path, dry_run: bool = False) -> dict:
    export = load_export(export_path)
    meta = export.get("metadata", {})
    npc_key = meta.get("npc_key") or export_path.stem.replace("_eval", "")
    npc_name = meta.get("npc_name") or npc_key
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    prefix = f"Unsloth_Core {npc_name} {stamp}"

    system_prompt = export["personas"][0]["system_prompt"]
    system_name = f"{prefix} System"
    if dry_run:
        print(f"DRY system: {system_name}")
        return {}

    text = server_action(
        session,
        f"/{WORKSPACE}/library/system-prompts",
        ACTIONS["create_system_prompt"],
        [WORKSPACE, {
            "name": system_name,
            "description": f"Unsloth_Core NPC system prompt for {npc_key}",
            "systemPrompt": system_prompt,
            "tags": ["unsloth-core", npc_key],
        }],
    )
    system_id = extract_id(text, system_name)
    print(f"Created system prompt: {npc_key} {system_id}")

    test_ids = []
    for qno, row in enumerate(flatten_questions(export), start=1):
        title = f"{prefix} Q{qno:02d} {row['category']}"
        prompt = row["question"]
        text = server_action(
            session,
            f"/{WORKSPACE}/library/test-prompts",
            ACTIONS["create_test_prompt"],
            [WORKSPACE, {
                "title": title,
                "description": f"{row['persona_name']} | {npc_key}",
                "prompt": prompt,
                "tags": ["unsloth-core", npc_key, row["category"]],
            }],
        )
        tid = extract_id(text, title)
        test_ids.append(tid)
        print(f"  Created test prompt {qno:02d}: {tid}")

    criteria = [
        {"id": str(uuid.uuid4()), "label": "Persona consistency", "description": "Maintains the NPC identity, voice, and role.", "weight": 3},
        {"id": str(uuid.uuid4()), "label": "Subject accuracy", "description": "Provides correct, grounded subject-matter information.", "weight": 3},
        {"id": str(uuid.uuid4()), "label": "Conciseness", "description": "Answers in 1-3 clear sentences without rambling.", "weight": 2},
        {"id": str(uuid.uuid4()), "label": "Natural dialogue", "description": "Sounds helpful, conversational, and suitable for Unity NPC dialogue.", "weight": 2},
        {"id": str(uuid.uuid4()), "label": "Safety and boundaries", "description": "Refuses unsafe/off-topic requests gracefully without AI disclaimers.", "weight": 2},
    ]
    config = {
        "defaultGeneratorModels": GENERATOR_MODELS,
        "evaluatorModels": EVALUATOR_MODELS,
        "systemPrompts": [system_id],
        "testPrompts": test_ids,
        "responsesPerTopicPerPersona": 1,
        "scoringMethod": "numeric",
        "criteria": criteria,
        "deterministicMode": True,
        "outputFormat": "json",
        "samplesPerPrompt": 1,
        "evaluationMethod": "rubric",
        "highConfidence": False,
        "failureHandling": {"mode": "continue"},
    }
    suite_name = f"{prefix} Blind Eval"
    text = server_action(
        session,
        f"/{WORKSPACE}/suites/create",
        ACTIONS["create_suite"],
        [WORKSPACE, {
            "name": suite_name,
            "description": f"Blind PeerLM eval for Unsloth_Core {npc_key}: 3 standard models, 25 prompts, Gemini Flash evaluator.",
            "configuration": config,
        }],
    )
    suite_id = extract_id(text, suite_name)
    print(f"Created suite: {npc_key} {suite_id}")
    return {"npc_key": npc_key, "system_id": system_id, "test_prompt_ids": test_ids, "suite_id": suite_id, "suite_name": suite_name}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exports", nargs="*", default=["peerlm/history_guide_eval.json", "peerlm/chef_assistant_eval.json"])
    ap.add_argument("--email", default=os.environ.get("PEERLM_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("PEERLM_PASSWORD"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output", default="peerlm/created_resources.json")
    args = ap.parse_args()

    if not args.email or not args.password:
        print("Set PEERLM_EMAIL and PEERLM_PASSWORD env vars, or pass --email/--password.", file=sys.stderr)
        return 2

    session = login(args.email, args.password)
    results = []
    for rel in args.exports:
        results.append(create_for_export(session, (PROJECT_ROOT / rel).resolve(), dry_run=args.dry_run))

    out = PROJECT_ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "resources": results}, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
