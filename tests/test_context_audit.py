from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.ops import context_audit

LEGACY_GENERATE_PATTERN = r"generate.*--technique ollama"


def _write_current_commands(root: Path, body: str) -> None:
    path = root / ".codex" / "references" / "current-commands.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_stale_generate_ollama_command_in_codex_current_commands_is_flagged(monkeypatch, tmp_path):
    monkeypatch.setattr(context_audit, "PROJECT_ROOT", tmp_path)
    _write_current_commands(
        tmp_path,
        """# Commands\n\n```bash\n./ucore generate data/npcs/specs/<npc>.json --technique ollama\n```\n""",
    )

    findings, _summary = context_audit.audit([".codex/references/current-commands.md"])

    assert any(
        finding.file == ".codex/references/current-commands.md"
        and finding.pattern == LEGACY_GENERATE_PATTERN
        and finding.severity == "error"
        for finding in findings
    )


def test_deprecated_avoid_generate_ollama_mention_is_allowed(monkeypatch, tmp_path):
    monkeypatch.setattr(context_audit, "PROJECT_ROOT", tmp_path)
    _write_current_commands(
        tmp_path,
        """# Deprecated / avoid\n\nDeprecated / avoid: do not use generate --technique ollama; use generate-ollama instead.\n""",
    )

    findings, _summary = context_audit.audit([".codex/references/current-commands.md"])

    assert not any(finding.pattern == LEGACY_GENERATE_PATTERN for finding in findings)


def test_instructions_audit_includes_stale_pattern_findings(monkeypatch, tmp_path):
    monkeypatch.setattr(context_audit, "PROJECT_ROOT", tmp_path)
    _write_current_commands(
        tmp_path,
        """# Commands\n\n```bash\n./ucore generate data/npcs/specs/<npc>.json --technique ollama\n```\n""",
    )

    findings, _summary = context_audit.audit(
        [".codex/references/current-commands.md"], instructions=True
    )

    assert any(finding.pattern == LEGACY_GENERATE_PATTERN for finding in findings)
