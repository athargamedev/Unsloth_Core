#!/usr/bin/env python3
"""
export_resume.py — resume/continue GGUF export for an NPC.

Usage:
  python scripts/export_resume.py chemistry_instructor
  python scripts/export_resume.py chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit --quantization q4_k_m
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Resume GGUF export for an NPC")
    parser.add_argument("npc_key", help="NPC key")
    parser.add_argument("--model", "-m", help="Base model ID")
    parser.add_argument("--quantization", default="q4_k_m", help="Quantization")
    parser.add_argument("--skip-f16", action="store_true", help="Skip f16 export")
    parser.add_argument("--timeout-seconds", type=int, default=5400, help="Per-variant timeout")
    args = parser.parse_args()

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "export.py"),
        args.npc_key,
        "--quantization",
        args.quantization,
        "--resume",
        "--timeout-seconds",
        str(args.timeout_seconds),
    ]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.skip_f16:
        cmd.append("--skip-f16")

    print("[export-resume] Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)


if __name__ == "__main__":
    main()
