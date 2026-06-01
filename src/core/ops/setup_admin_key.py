#!/usr/bin/env python3
"""
Generate the initial admin API key for the Unsloth_Core dashboard.

This script creates the first admin API key directly in the pipeline database
so the dashboard auth middleware can validate subsequent requests. After this
key is created, additional keys can be managed via the /api/auth/keys endpoints.

Usage:
    python scripts/ops/setup_admin_key.py
    python scripts/ops/setup_admin_key.py --db-url postgresql://postgres:postgres@localhost:15434/postgres

Dependencies:
    - Python 3.8+
    - `pip install bcrypt` (if not already installed; falls back to a Node.js subprocess)
    - Node.js with `bcrypt` npm package installed in frontend_control/

The generated key is printed to stdout once. Save it securely — it cannot be
retrieved from the database later (only the bcrypt hash is stored).
"""

import argparse
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_DB_URL = "postgresql://postgres:postgres@localhost:15434/postgres"
DASHBOARD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend_control",
    "unity-npc-llm-training-dashboard",
)

# ── Helpers ─────────────────────────────────────────────────────────────────


def _find_node() -> str | None:
    """Find Node.js executable on this system.

    Checks PATH first, then common installation locations, then nvm-managed
    versions. Returns the first viable path or None if not found.
    """
    # 1. Check PATH
    node = shutil.which("node")
    if node:
        return node

    # 2. Check common static locations
    common_paths = [
        "/usr/bin/node",
        "/usr/local/bin/node",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p

    # 3. Check nvm-managed installations (~/.nvm/versions/node/*/bin/node)
    nvm_dir = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm_dir):
        versions = sorted(os.listdir(nvm_dir), reverse=True)
        for v in versions:
            candidate = os.path.join(nvm_dir, v, "bin", "node")
            if os.path.isfile(candidate):
                return candidate

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the initial admin API key for the Unsloth_Core dashboard."
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DB_URL),
        help=f"PostgreSQL connection URL (default: {DEFAULT_DB_URL})",
    )
    return parser.parse_args()


def hash_with_bcrypt_python(key: str) -> str:
    """Hash a key using Python's bcrypt package."""
    import bcrypt  # noqa: PLC0415 — imported lazily for fallback

    return bcrypt.hashpw(key.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def hash_with_bcrypt_node(key: str) -> str:
    """Hash a key by invoking the Node.js bcrypt package via subprocess.

    The key is passed through stdin to avoid leaking it into the process
    environment (which is visible to other processes via /proc/PID/environ).
    """
    node_path = _find_node()
    if not node_path:
        raise RuntimeError(
            "Node.js not found on PATH or at any common location. "
            "Install Node.js or run:  pip install bcrypt"
        )

    node_script = """
        const bcrypt = require('bcrypt');
        const chunks = [];
        process.stdin.on('data', c => chunks.push(c));
        process.stdin.on('end', () => {
            const key = Buffer.concat(chunks).toString().trim();
            bcrypt.hash(key, 10).then(hash => process.stdout.write(hash));
        });
    """
    try:
        result = subprocess.run(
            [node_path, "-e", node_script],
            input=key.encode("utf-8"),
            capture_output=True,
            cwd=DASHBOARD_DIR,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Node.js subprocess failed: {result.stderr.strip()}")
        hashed = result.stdout.strip().decode("utf-8")
        if not hashed:
            raise RuntimeError("Node.js subprocess produced empty output")
        return hashed
    except FileNotFoundError as e:
        # Distinguish between a missing node executable and a bad cwd
        if node_path and not os.path.isfile(node_path):
            msg = "Node.js not found at resolved path."
        elif not os.path.isdir(DASHBOARD_DIR):
            msg = f"Dashboard directory does not exist: {DASHBOARD_DIR}"
        else:
            msg = f"Subprocess failed to start: {e}"
        raise RuntimeError(
            f"{msg} "
            "Install Node.js or run:  pip install bcrypt"
        ) from None


def hash_api_key(key: str) -> str:
    """Hash the API key. Prefers Python bcrypt, falls back to Node.js."""
    try:
        return hash_with_bcrypt_python(key)
    except ImportError:
        print("[INFO] Python bcrypt not available — falling back to Node.js subprocess.")
        return hash_with_bcrypt_node(key)


def insert_key(db_url: str, key_hash: str, prefix: str, name: str, role: str) -> None:
    """Insert the API key record into the pipeline database."""
    import psycopg  # noqa: PLC0415 — imported here to keep top-level clean

    conn = psycopg.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_keys (key_hash, key_prefix, name, role, is_active)
                VALUES (%s, %s, %s, %s, true)
                """,
                (key_hash, prefix, name, role),
            )
        conn.commit()
    finally:
        conn.close()


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    # Generate a cryptographically secure 64-char hex key
    raw_key = secrets.token_hex(32)  # 32 bytes → 64 hex chars
    prefix = raw_key[:8]

    try:
        key_hash = hash_api_key(raw_key)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        print(
            "Install Python bcrypt:  pip install bcrypt",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        insert_key(args.db_url, key_hash, prefix, "admin", "admin")
    except ImportError:
        print(
            "[ERROR] psycopg (PostgreSQL driver) is not installed.",
            file=sys.stderr,
        )
        print("Install it:  pip install psycopg", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to insert API key into database: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Output ──────────────────────────────────────────────────────────────
    line = "=" * 70
    print(f"""
{line}
Admin API Key Generated
{line}

Key:      {raw_key}
Prefix:   {prefix}
Name:     admin
Role:     admin

Save this key immediately. It cannot be retrieved later.
Use it in the Authorization header: Bearer <key>
{line}
""")


if __name__ == "__main__":
    main()
