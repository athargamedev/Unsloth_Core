from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MODEL_PRESETS_PATH = PROJECT_ROOT / "configs" / "model-presets.yaml"
DEFAULT_FALLBACK_PRESET = "safe-any"


def load_model_preset_map() -> dict[str, Any]:
    if not MODEL_PRESETS_PATH.exists():
        return {}
    with MODEL_PRESETS_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def infer_model_bucket(model_name: str | None) -> str:
    model = (model_name or "").lower()
    if "8b" in model:
        return "8b"
    if "7b" in model:
        return "7b"
    if "3b" in model:
        return "3b"
    if "1.7b" in model:
        return "1.7b"
    if "1b" in model:
        return "1b"
    if "0.5b" in model:
        return "0.5b"
    return "3b"


def resolve_training_preset(
    model_name: str | None,
    *,
    preset: str | None = None,
    spec_preset: str | None = None,
) -> str:
    """Resolve the effective training preset for a model.

    Priority order:
    1. Explicit CLI preset
    2. Spec-defined preset
    3. Exact model match in configs/model-presets.yaml
    4. Bucket match in configs/model-presets.yaml
    5. Default map fallback
    6. safe-any as the last safety net
    """
    if preset:
        return preset
    if spec_preset:
        return spec_preset

    mapping = load_model_preset_map()
    exact = (mapping.get("exact_models") or {}).get(model_name or "")
    if isinstance(exact, str) and exact.strip():
        return exact.strip()

    bucket = infer_model_bucket(model_name)
    bucket_map = mapping.get("buckets") or {}
    resolved = bucket_map.get(bucket)
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()

    default = mapping.get("default")
    if isinstance(default, str) and default.strip():
        return default.strip()

    return DEFAULT_FALLBACK_PRESET
