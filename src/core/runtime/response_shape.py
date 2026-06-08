"""Runtime response-shape guards for Unity NPC answers."""

from __future__ import annotations

import re

_ABBREVIATIONS = (
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "Sr.",
    "Jr.",
    "St.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
)
_ABBREVIATIONS_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(re.escape(abbrev) for abbrev in _ABBREVIATIONS) + r")",
    flags=re.IGNORECASE,
)
_INITIALISM_PATTERN = re.compile(r"\b(?:[A-Za-z]\.){2,}")


def _mask_sentence_internal_periods(text: str) -> str:
    cleaned = _ABBREVIATIONS_PATTERN.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    cleaned = _INITIALISM_PATTERN.sub(lambda m: m.group(0).replace(".", "\x00"), cleaned)
    return cleaned.replace("...", "\x00\x00\x00")


def count_sentences(text: str) -> int:
    """Count sentence-like units while preserving common abbreviations."""
    if not text:
        return 0
    cleaned = _mask_sentence_internal_periods(text)
    return len([s for s in re.split(r"[.!?]+", cleaned) if s.strip()])


def trim_to_max_sentences(text: str, max_sentences: int) -> str:
    """Trim text to max_sentences without splitting common abbreviations."""
    if not text or max_sentences <= 0:
        return ""

    cleaned = _mask_sentence_internal_periods(text)
    matches = list(re.finditer(r"[.!?]+", cleaned))
    if len(matches) < max_sentences:
        trimmed = text.strip()
    else:
        trimmed = text[: matches[max_sentences - 1].end()].strip()

    if trimmed and trimmed[-1] not in ".!?":
        trimmed += "."
    return trimmed


def spec_max_sentences(spec: dict | None, default: int = 3) -> int:
    """Read the runtime sentence cap from an NPC spec dialogue block."""
    if not isinstance(spec, dict):
        return default
    dialogue = spec.get("dialogue")
    if not isinstance(dialogue, dict):
        return default
    value = dialogue.get("max_sentences", default)
    return value if isinstance(value, int) and value > 0 else default


def apply_runtime_sentence_guard(
    text: str, spec: dict | None = None, max_sentences: int | None = None
) -> tuple[str, dict[str, int | bool]]:
    """Return a runtime-safe response plus metadata about the clamp.

    This is a deterministic final-shape guard, not a semantic rewrite: it only
    trims after the configured sentence cap so Unity-facing output cannot exceed
    the NPC runtime dialogue contract.
    """
    cap = max_sentences if max_sentences is not None else spec_max_sentences(spec)
    before = count_sentences(text)
    shaped = trim_to_max_sentences(text, cap)
    after = count_sentences(shaped)
    return shaped, {
        "runtime_guard_applied": shaped != (text or ""),
        "runtime_guard_max_sentences": cap,
        "runtime_guard_raw_sentences": before,
        "runtime_guard_sentences": after,
    }
