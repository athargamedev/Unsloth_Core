import re

from src.core.ops import context_audit


def test_deprecated_ollama_generate_pattern_flags_unlabelled_command() -> None:
    pattern = context_audit.DEPRECATED_OLLAMA_GENERATE_PATTERN
    line = "./ucore generate data/npcs/specs/history_guide.json --technique ollama"

    assert re.search(pattern, line, flags=re.IGNORECASE)
    assert not context_audit.is_allowed(line, pattern)


def test_deprecated_ollama_generate_pattern_allows_legacy_or_avoid_label() -> None:
    pattern = context_audit.DEPRECATED_OLLAMA_GENERATE_PATTERN

    legacy_line = "legacy ./ucore generate --technique ollama path"
    avoid_line = "avoid ./ucore generate --technique ollama; use generate-ollama"

    assert re.search(pattern, legacy_line, flags=re.IGNORECASE)
    assert context_audit.is_allowed(legacy_line, pattern)
    assert context_audit.is_allowed(avoid_line, pattern)
