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

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILES = [
    "AGENTS.md",
    "README.md",
    "docs/project-state.md",
    "docs/training-workflow.md",
    "MIGRATION_NOTES.md",
]

# Regex, severity, message for legacy paths migrated in Phases 3-5.
LEGACY_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bconfigs/presets\b|\bconfigs/base_configs\b", "warn", "legacy configs preset/base path mentioned; should be etc/presets/ or etc/base_models/"),
    (r"\bsubjects/NPC_specs\b", "warn", "legacy specs path subjects/NPC_specs mentioned; should be data/npcs/specs/"),
    (r"\bsubjects/reference_docs\b", "warn", "legacy reference docs path subjects/reference_docs mentioned; should be data/npcs/reference_docs/"),
    (r"\bsubjects/schemas\b", "warn", "legacy schemas path subjects/schemas mentioned; should be data/npcs/schemas/"),
    (r"\bsubjects/datasets\b", "warn", "legacy datasets path subjects/datasets mentioned; should be data/datasets/"),
    (r"\boutputs/", "warn", "legacy outputs path outputs/ mentioned; should be artifacts/models/"),
    (r"(?<!artifacts/)\bexports/", "warn", "legacy exports path exports/ mentioned; should be artifacts/exports/"),
    (r"(?<!artifacts/)\beval/", "warn", "legacy eval path eval/ mentioned; should be artifacts/eval/"),
    (r"(?<!artifacts/)\blogs/", "warn", "legacy logs path logs/ mentioned; should be artifacts/logs/"),
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
] + LEGACY_PATTERNS

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
        is_migration_notes = rel.lower() == "migration_notes.md"
        for idx, line in enumerate(text.splitlines(), start=1):
            for pattern, severity, message in PATTERNS:
                # Skip legacy path validation patterns for migration notes file
                if is_migration_notes and pattern in (lp[0] for lp in LEGACY_PATTERNS):
                    continue
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
