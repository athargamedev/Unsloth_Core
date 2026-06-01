#!/usr/bin/env python3
"""Audit project context files for stale Unsloth_Core references.

This is a lightweight hygiene check for agent-facing docs. It is intentionally
rule-based: update PATTERNS when deprecated project references change.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES = [
    "AGENTS.md",
    "README.md",
    "docs/PROJECT_STATE.md",
    "docs/TRAINING_WORKFLOW_CONTEXT.md",
    ".hermes/README.md",
    ".hermes/memories/unsloth_core_project_memory.md",
]

# Regex, severity, message. Keep these focused on references that caused drift.
PATTERNS: list[tuple[str, str, str]] = [
    (r"astronomy_guide|fitness_coach", "warn", "inactive NPC mentioned; ensure it is labelled deprecated, not active"),
    (r"Production Train.*--technique template|production.*--technique template|--technique template.*production", "error", "template generation must not be presented as production training"),
    (r"qwen3:latest", "warn", "qwen3 appears; current local tested default is qwen2.5:7b unless re-verified"),
    (r"npm run dev:modular", "warn", "old dashboard command; current package uses npm run dev from dashboard directory"),
    (r"server-modular\.ts", "warn", "old modular entrypoint reference; verify against current dashboard package before using"),
    (r"auto-retrain.*6GB|6GB.*auto-retrain", "warn", "auto-retrain on 6GB can collide with Ollama/training VRAM"),
    (r"npc-fit/", "error", "old HF namespace; use andreathar/ or TWLgames/"),
]

ALLOWED_CONTEXT = {
    "astronomy_guide": ["deprecated", "inactive", "avoid", "do not"],
    "fitness_coach": ["deprecated", "inactive", "avoid", "do not"],
    "qwen3:latest": ["deprecated", "avoid", "unless re-verified", "older docs", "experimental", "legacy", "not the local default"],
}

@dataclass
class Finding:
    file: str
    line: int
    severity: str
    pattern: str
    message: str
    text: str


def iter_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = PROJECT_ROOT / raw
        if path.is_dir():
            files.extend(p for p in path.rglob("*.md") if "node_modules" not in p.parts)
        elif path.exists():
            files.append(path)
    return sorted(set(files))


def is_allowed(line: str, pattern: str) -> bool:
    lower = line.lower()
    for token, allowed_words in ALLOWED_CONTEXT.items():
        if token in pattern or token in line:
            return any(word in lower for word in allowed_words)
    return False


def audit(paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        for idx, line in enumerate(text.splitlines(), start=1):
            for pattern, severity, message in PATTERNS:
                if re.search(pattern, line, flags=re.IGNORECASE) and not is_allowed(line, pattern):
                    findings.append(Finding(rel, idx, severity, pattern, message, line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit agent context for stale references")
    parser.add_argument("paths", nargs="*", default=DEFAULT_FILES, help="Files or directories to audit")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    findings = audit(args.paths)
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print("context_audit: ok")
        for f in findings:
            print(f"{f.severity.upper()} {f.file}:{f.line}: {f.message}")
            print(f"  {f.text}")

    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
