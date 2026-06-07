#!/usr/bin/env python3
"""Audit project context files for stale references and freshness.

Two modes:
  (default) Pattern-based stale-reference scanner for agent context files.
  --instructions-audit  Extended audit: YAML frontmatter freshness, brief completeness,
                        line limits, and legacy-path detection.

Usage:
  python src/core/ops/context_audit.py [paths...]
  python src/core/ops/context_audit.py --instructions-audit [paths...]
  python src/core/ops/context_audit.py --json [paths...]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILES: list[str] = [
    "AGENTS.md",
    "README.md",
    "SETUP.md",
    "CONTRIBUTING.md",
    "docs/project-state.md",
    "docs/training-workflow.md",
    "MIGRATION_NOTES.md",
]

# Regex, severity, message for legacy paths migrated in Phases 3-5.
LEGACY_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"from scripts\b|import scripts\b",
        "error",
        "legacy scripts/ import used; should use canonical src.core paths",
    ),
    (
        r"\bconfigs/presets\b|\bconfigs/base_configs\b",
        "warn",
        "legacy configs preset/base path mentioned; should be etc/presets/ or etc/base_models/",
    ),
    (
        r"\bsubjects/NPC_specs\b",
        "warn",
        "legacy specs path subjects/NPC_specs mentioned; should be data/npcs/specs/",
    ),
    (
        r"\bsubjects/reference_docs\b",
        "warn",
        "legacy reference docs path subjects/reference_docs mentioned; should be data/npcs/reference_docs/",
    ),
    (
        r"\bsubjects/schemas\b",
        "warn",
        "legacy schemas path subjects/schemas mentioned; should be data/npcs/schemas/",
    ),
    (
        r"\bsubjects/datasets\b",
        "warn",
        "legacy datasets path subjects/datasets mentioned; should be data/datasets/",
    ),
    (r"\boutputs/", "warn", "legacy outputs path outputs/ mentioned; should be artifacts/models/"),
    (
        r"(?<!artifacts/)\bexports/",
        "warn",
        "legacy exports path exports/ mentioned; should be artifacts/exports/",
    ),
    (
        r"(?<!artifacts/)\beval/",
        "warn",
        "legacy eval path eval/ mentioned; should be artifacts/eval/",
    ),
    (
        r"(?<!artifacts/)\blogs/",
        "warn",
        "legacy logs path logs/ mentioned; should be artifacts/logs/",
    ),
]

# Regex, severity, message. Keep these focused on references that caused drift.
DEPRECATED_OLLAMA_GENERATE_PATTERN = (
    r"\./ucore\s+generate\b(?=[^`\n]*--technique\s+ollama)"
)

PATTERNS: list[tuple[str, str, str]] = [
    (
        DEPRECATED_OLLAMA_GENERATE_PATTERN,
        "error",
        "deprecated production generation command; use ./ucore generate-ollama ... --model qwen2.5:7b --fresh",
    ),
    (
        r"astronomy_guide|fitness_coach",
        "warn",
        "inactive NPC mentioned; ensure it is labelled deprecated, not active",
    ),
    (
        r"Production Train.*--technique template|production.*--technique template|--technique template.*production",
        "error",
        "template generation must not be presented as production training",
    ),
    (
        r"qwen3:latest",
        "warn",
        "qwen3 appears; current local tested default is qwen2.5:7b unless re-verified",
    ),
    (
        r"npm run dev:modular",
        "warn",
        "old dashboard command; current package uses npm run dev from dashboard directory",
    ),
    (
        r"server-modular\.ts",
        "warn",
        "old modular entrypoint reference; verify against current dashboard package before using",
    ),
    (
        r"auto-retrain.*6GB|6GB.*auto-retrain",
        "warn",
        "auto-retrain on 6GB can collide with Ollama/training VRAM",
    ),
    (
        r"generate.*--technique ollama",
        "error",
        "legacy production generation command; use ./ucore generate-ollama instead",
    ),
    (r"npc-fit/", "error", "old HF namespace; use andreathar/ or TWLgames/"),
] + LEGACY_PATTERNS

ALLOWED_CONTEXT: dict[str, list[str]] = {
    "astronomy_guide": ["deprecated", "inactive", "avoid", "do not"],
    "fitness_coach": ["deprecated", "inactive", "avoid", "do not"],
    "qwen3:latest": [
        "deprecated",
        "avoid",
        "unless re-verified",
        "older docs",
        "experimental",
        "legacy",
        "not the local default",
    ],
    "generate.*--technique ollama": [
        "deprecated",
        "avoid",
        "do not",
        "don't",
        "legacy",
        "not use",
        "instead",
        "use generate-ollama",
        "differ from",
        "differs from",
    ],
}

STALE_DAYS = 30  # docs / instructions files
AGENTS_LINE_LIMIT = 150  # soft limit


@dataclass
class Finding:
    file: str
    line: int
    severity: str
    pattern: str
    message: str
    text: str


@dataclass
class AuditSummary:
    stale_docs: int = 0
    missing_frontmatter: int = 0
    missing_version: int = 0
    missing_last_verified: int = 0
    agents_lines: int = 0
    legacy_path_warnings: int = 0
    other_issues: int = 0


# ── helpers ──────────────────────────────────────────────────────────────


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
    if pattern == DEPRECATED_OLLAMA_GENERATE_PATTERN:
        return any(word in lower for word in ("legacy", "avoid"))
    for token, allowed_words in ALLOWED_CONTEXT.items():
        if token in pattern or token in line:
            return any(word in lower for word in allowed_words)
    return False


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter (between --- delimiters) as a dict.

    Returns {} if no valid frontmatter is found.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1
    if end >= len(lines):
        return {}  # never closed
    body = "\n".join(lines[1:end])
    if yaml is not None:
        try:
            result = yaml.safe_load(body)
            return result if isinstance(result, dict) else {}
        except yaml.YAMLError:
            return {}
    # fallback: naïve key:value parser
    data: dict = {}
    for line in body.splitlines():
        m = re.match(r"^(\w[\w_-]*)\s*:\s*(.*?)\s*$", line)
        if m:
            data[m.group(1)] = m.group(2).strip("\"'")
    return data


# ── scanners ─────────────────────────────────────────────────────────────


def _pattern_scan(paths: list[str]) -> list[Finding]:
    """Existing stale-pattern scanner."""
    findings: list[Finding] = []
    legacy_pattern_strs = {lp[0] for lp in LEGACY_PATTERNS}
    for path in iter_files(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        is_migration_notes = rel.lower() == "migration_notes.md"
        for idx, line in enumerate(text.splitlines(), start=1):
            for pattern, severity, message in PATTERNS:
                if is_migration_notes and pattern in legacy_pattern_strs:
                    continue
                if re.search(pattern, line, flags=re.IGNORECASE) and not is_allowed(line, pattern):
                    findings.append(Finding(rel, idx, severity, pattern, message, line.strip()))
    return findings


def _instructions_scan(files: list[Path], base_path: Path) -> list[Finding]:
    """Extended scan for frontmatter freshness, brief completeness, and line limits."""
    findings: list[Finding] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(base_path).as_posix()
        fm = parse_frontmatter(text)
        is_brief = rel.startswith(".hermes/agents/") or rel.startswith(".codex/agents/")

        # ── AGENTS.md line limit ──
        if rel == "AGENTS.md":
            line_count = len(text.splitlines())
            if line_count > AGENTS_LINE_LIMIT:
                findings.append(
                    Finding(
                        file=rel,
                        line=0,
                        severity="warn",
                        pattern="agents_line_limit",
                        message=f"AGENTS.md is {line_count} lines (soft limit: {AGENTS_LINE_LIMIT})",
                        text="",
                    )
                )

        # ── frontmatter freshness ──
        if fm.get("last_verified"):
            last_str = str(fm["last_verified"])
            try:
                last = datetime.strptime(last_str, "%Y-%m-%d").replace(tzinfo=UTC)
                days = (datetime.now(UTC) - last).days
                if days > STALE_DAYS:
                    findings.append(
                        Finding(
                            file=rel,
                            line=0,
                            severity="warn",
                            pattern="stale_frontmatter",
                            message=f"last_verified {last_str} is {days} days old (>{STALE_DAYS})",
                            text="",
                        )
                    )
            except ValueError:
                findings.append(
                    Finding(
                        file=rel,
                        line=0,
                        severity="warn",
                        pattern="bad_date_format",
                        message=f"last_verified '{last_str}' is not a valid YYYY-MM-DD date",
                        text="",
                    )
                )
        elif fm:  # has frontmatter but no last_verified
            findings.append(
                Finding(
                    file=rel,
                    line=0,
                    severity="warn",
                    pattern="missing_last_verified",
                    message="Has frontmatter but missing last_verified",
                    text="",
                )
            )

        # ── agent brief completeness ──
        if is_brief:
            if "version" not in fm:
                findings.append(
                    Finding(
                        file=rel,
                        line=0,
                        severity="error",
                        pattern="missing_version",
                        message="Agent brief missing version in frontmatter",
                        text="",
                    )
                )
            if "last_verified" not in fm:
                findings.append(
                    Finding(
                        file=rel,
                        line=0,
                        severity="warn",
                        pattern="missing_brief_verified",
                        message="Agent brief missing last_verified in frontmatter",
                        text="",
                    )
                )
            if "source_order" not in fm:
                findings.append(
                    Finding(
                        file=rel,
                        line=0,
                        severity="warn",
                        pattern="missing_source_order",
                        message="Agent brief missing source_order in frontmatter",
                        text="",
                    )
                )

        # ── skill frontmatter completeness ──
        is_skill = ".hermes/skills/" in rel or ".codex/skills/" in rel
        if is_skill and "last_verified" not in fm:
            findings.append(
                Finding(
                    file=rel,
                    line=0,
                    severity="warn",
                    pattern="missing_skill_verified",
                    message="Skill missing last_verified in frontmatter",
                    text="",
                )
            )

    return findings


def audit(paths: list[str], instructions: bool = False) -> tuple[list[Finding], AuditSummary]:
    """Run all scanners and produce findings + summary."""
    findings = _pattern_scan(paths)

    if instructions:
        # Scan all relevant files for instructions-audit
        scan_paths: list[Path] = []
        for raw in paths:
            p = PROJECT_ROOT / raw
            if p.is_dir():
                scan_paths.extend(pp for pp in p.rglob("*.md") if "node_modules" not in pp.parts)
            elif p.exists():
                scan_paths.append(p)
        scan_paths = sorted(set(scan_paths))
        findings.extend(_instructions_scan(scan_paths, PROJECT_ROOT))

    summary = _compute_summary(findings, paths)
    return findings, summary


def _compute_summary(findings: list[Finding], _paths: list[str]) -> AuditSummary:
    s = AuditSummary()
    for f in findings:
        if f.pattern in ("stale_frontmatter",):
            s.stale_docs += 1
        elif f.pattern in ("missing_version",):
            s.missing_version += 1
        elif f.pattern in (
            "missing_last_verified",
            "missing_brief_verified",
            "missing_skill_verified",
        ):
            s.missing_last_verified += 1
        elif f.pattern == "agents_line_limit":
            # captured via agents_lines below
            pass
        elif f.pattern.startswith("legacy") or any(
            leg_pat[0] == f.pattern for leg_pat in LEGACY_PATTERNS
        ):
            s.legacy_path_warnings += 1
        else:
            s.other_issues += 1

    # Read AGENTS.md line count for summary
    agents_path = PROJECT_ROOT / "AGENTS.md"
    if agents_path.exists():
        s.agents_lines = len(agents_path.read_text(encoding="utf-8").splitlines())

    return s


def _format_summary(s: AuditSummary) -> str:
    parts: list[str] = []
    if s.stale_docs:
        parts.append(f"{s.stale_docs} docs over {STALE_DAYS}d stale")
    else:
        parts.append("0 stale docs")
    brief_issues = s.missing_version + s.missing_last_verified
    if brief_issues:
        parts.append(f"{brief_issues} brief frontmatter gaps")
    else:
        parts.append("0 brief frontmatter gaps")
    if s.legacy_path_warnings:
        parts.append(f"{s.legacy_path_warnings} legacy path warnings")
    else:
        parts.append("0 legacy path warnings")
    if s.agents_lines:
        status = "OK" if s.agents_lines <= AGENTS_LINE_LIMIT else "OVER"
        parts.append(f"AGENTS.md {status} ({s.agents_lines} lines)")
    return " | ".join(parts)


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit agent context for stale references and freshness"
    )
    parser.add_argument(
        "paths", nargs="*", default=DEFAULT_FILES, help="Files or directories to audit"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--instructions-audit",
        action="store_true",
        help="Run extended freshness and completeness audit",
    )
    args = parser.parse_args()

    findings, summary = audit(args.paths, instructions=args.instructions_audit)

    if args.json:
        output = {
            "findings": [asdict(f) for f in findings],
            "summary": asdict(summary),
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        if not findings and not args.instructions_audit:
            print("context_audit: ok")
        for f in findings:
            line_info = f":{f.line}" if f.line else ""
            print(f"{f.severity.upper()} {f.file}{line_info}: {f.message}")
            if f.text:
                print(f"  {f.text}")

        if args.instructions_audit:
            print(f"\ncontext_audit: instructions audit  {_format_summary(summary)}")

    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
