#!/usr/bin/env python3
"""Report Docker/Supabase core runtime status for Unsloth_Core.

Usage:
  python src/core/ops/docker_core_status.py
  python src/core/ops/docker_core_status.py --watchdog

Normal mode prints a compact operator status.
Watchdog mode prints only when something is down/degraded or the status changed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PROJECT = "LLM_WSL"
STATE_FILE = Path.home() / ".cache" / "unsloth_core_docker_core_status.json"
EXPECTED = [
    "supabase_db_LLM_WSL",
    "supabase_kong_LLM_WSL",
    "supabase_studio_LLM_WSL",
    "supabase_auth_LLM_WSL",
    "supabase_rest_LLM_WSL",
    "supabase_realtime_LLM_WSL",
    "supabase_storage_LLM_WSL",
    "supabase_pg_meta_LLM_WSL",
    "supabase_analytics_LLM_WSL",
    "supabase_inbucket_LLM_WSL",
    "supabase_vector_LLM_WSL",
]
PORTS = {
    "API/Kong": "http://127.0.0.1:16433",
    "Studio": "http://127.0.0.1:16434",
    "Analytics": "http://127.0.0.1:16435",
    "Inbucket": "http://127.0.0.1:16436",
    "Postgres": "127.0.0.1:15433",
}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=15)


def docker_rows() -> list[dict[str, str]]:
    fmt = "{{.Names}}\t{{.Status}}\t{{.Ports}}"
    proc = run(["docker", "ps", "--format", fmt])
    if proc.returncode != 0:
        return [
            {
                "name": "docker",
                "status": f"ERROR: {proc.stderr.strip() or proc.stdout.strip()}",
                "ports": "",
            }
        ]
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            rows.append({"name": parts[0], "status": parts[1], "ports": parts[2]})
    return rows


def summarize() -> dict:
    rows = docker_rows()
    by_name = {r["name"]: r for r in rows}
    missing = [name for name in EXPECTED if name not in by_name]
    unhealthy = [
        r
        for name, r in by_name.items()
        if name in EXPECTED
        and (
            "unhealthy" in r["status"].lower()
            or "restarting" in r["status"].lower()
            or not r["status"].startswith("Up")
        )
    ]
    running = [name for name in EXPECTED if name in by_name]
    healthy = [name for name in running if name not in {r["name"] for r in unhealthy}]
    ok = not missing and not unhealthy
    return {
        "ok": ok,
        "running": running,
        "healthy": healthy,
        "missing": missing,
        "unhealthy": unhealthy,
        "rows": rows,
    }


def render(summary: dict) -> str:
    mark = "✅" if summary["ok"] else "⚠️"
    lines = [
        f"{mark} Docker core / Supabase project {PROJECT}: {len(summary['healthy'])}/{len(EXPECTED)} services up"
    ]
    if summary["missing"]:
        lines.append("Missing: " + ", ".join(summary["missing"]))
    if summary["unhealthy"]:
        lines.append("Unhealthy:")
        for row in summary["unhealthy"]:
            lines.append(f"  - {row['name']}: {row['status']}")
    lines.append("Ports:")
    for label, value in PORTS.items():
        lines.append(f"  - {label}: {value}")
    lines.append("Containers:")
    for name in EXPECTED:
        row = next((r for r in summary["rows"] if r["name"] == name), None)
        if row:
            lines.append(f"  - {name}: {row['status']}")
        else:
            lines.append(f"  - {name}: DOWN")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchdog", action="store_true", help="silent when healthy and unchanged")
    args = parser.parse_args()

    summary = summarize()
    digest = {
        "ok": summary["ok"],
        "missing": summary["missing"],
        "unhealthy": [(r["name"], r["status"]) for r in summary["unhealthy"]],
    }

    if args.watchdog:
        previous = None
        if STATE_FILE.exists():
            try:
                previous = json.loads(STATE_FILE.read_text())
            except Exception:
                previous = None
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(digest, sort_keys=True))
        if summary["ok"] and previous == digest:
            return 0
        if summary["ok"] and previous is None:
            return 0

    print(render(summary))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
