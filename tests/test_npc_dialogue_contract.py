import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NPC_SPEC_DIR = PROJECT_ROOT / "subjects" / "NPC_specs"

MAX_SENTENCES_LIMIT = 5
MAX_CHARACTERS_LIMIT = 800


def _iter_specs():
    for spec_path in sorted(NPC_SPEC_DIR.glob("*.json")):
        with spec_path.open(encoding="utf-8") as handle:
            yield spec_path, json.load(handle)


def test_npc_dialogue_limits_remain_runtime_friendly():
    violations = []
    for spec_path, spec in _iter_specs():
        dialogue = spec.get("dialogue") or {}
        max_sentences = int(dialogue.get("max_sentences", 0) or 0)
        max_characters = int(dialogue.get("max_characters", 0) or 0)
        if max_sentences > MAX_SENTENCES_LIMIT or max_characters > MAX_CHARACTERS_LIMIT:
            violations.append(
                {
                    "spec": spec_path.name,
                    "max_sentences": max_sentences,
                    "max_characters": max_characters,
                }
            )

    assert not violations, (
        "NPC dialogue limits are too loose for Unity runtime: "
        f"{violations}. Keep limits runtime-friendly instead of widening them to force generation success."
    )


def test_npc_system_prompts_still_request_short_ui_friendly_answers():
    prompts_without_shortness = []
    for spec_path, spec in _iter_specs():
        system_prompt = str(spec.get("system_prompt", ""))
        if not system_prompt:
            prompts_without_shortness.append(spec_path.name)
            continue
        lower_prompt = system_prompt.lower()
        if not any(keyword in lower_prompt for keyword in ("short", "1-3", "concise", "brief", "game ui", "ui friendly")):
            prompts_without_shortness.append(spec_path.name)

    assert not prompts_without_shortness, (
        "System prompts should keep NPC responses short and UI-friendly: "
        f"{prompts_without_shortness}"
    )
