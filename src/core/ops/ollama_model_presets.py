from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config.constants import DEFAULT_JUDGE_MODEL

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OLLAMA_MODEL_PRESETS_PATH = PROJECT_ROOT / "configs" / "ollama-model-presets.yaml"
DEFAULT_GENERATION_PRESET = "generate-qwen25"
DEFAULT_JUDGE_PRESET = "judge-qwen25"


def load_ollama_model_preset_map() -> dict[str, Any]:
    if not OLLAMA_MODEL_PRESETS_PATH.exists():
        return {}
    with OLLAMA_MODEL_PRESETS_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_ollama_model(*, preset: str | None = None, model: str | None = None, role: str = "generation") -> str:
    """Resolve the effective Ollama model for generation or judging.

    Priority order:
    1. Explicit CLI model
    2. Explicit CLI preset
    3. Role-specific default preset from configs/ollama-model-presets.yaml
    4. Role-specific default model mapping
    5. Safety fallback to DEFAULT_JUDGE_MODEL for judging, qwen2.5:7b for generation
    """
    if model:
        return model.strip()

    mapping = load_ollama_model_preset_map()
    role = role if role in {"generation", "judge"} else "generation"
    role_map = mapping.get(role) or {}

    chosen_preset = preset or mapping.get(f"default_{role}")
    if isinstance(chosen_preset, str) and chosen_preset.strip():
        chosen_model = role_map.get(chosen_preset.strip())
        if isinstance(chosen_model, str) and chosen_model.strip():
            return chosen_model.strip()

    default_preset = mapping.get(f"default_{role}")
    if isinstance(default_preset, str) and default_preset.strip():
        chosen_model = role_map.get(default_preset.strip())
        if isinstance(chosen_model, str) and chosen_model.strip():
            return chosen_model.strip()

    if role == "judge":
        return DEFAULT_JUDGE_MODEL
    return "qwen2.5:7b"
