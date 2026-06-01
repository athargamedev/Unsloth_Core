from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

_SAFE_RE = re.compile(r"[^a-z0-9]+")


def slugify_artifact_part(value: str, max_length: int = 48) -> str:
    """Return a short lowercase filename-safe slug for a model/preset part."""
    text = str(value).split("/")[-1].lower()
    text = text.replace(":", "-")
    text = _SAFE_RE.sub("-", text).strip("-")
    text = re.sub(r"-+", "-", text)
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip("-")


def canonical_params_json(params: dict[str, Any] | None) -> str:
    """Stable JSON for hashing parameter dictionaries."""
    return json.dumps(params or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def params_hash(params: dict[str, Any] | None, length: int = 6) -> str:
    """Short deterministic hash for generation/train/eval params."""
    return hashlib.sha256(canonical_params_json(params).encode("utf-8")).hexdigest()[:length]


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify_npc_key(value: str, max_length: int = 40) -> str:
    text = re.sub(r"[^a-z0-9_]+", "_", str(value).lower()).strip("_")
    text = re.sub(r"_+", "_", text)
    return text[:max_length].rstrip("_")


def build_artifact_id(
    *,
    npc_key: str,
    dataset_technique: str,
    base_model: str,
    generation_preset: str,
    training_preset: str,
    eval_model: str,
    params: dict[str, Any] | None = None,
    timestamp: str | None = None,
    max_length: int = 180,
) -> str:
    """Build readable artifact/run/eval/export ID.

    Format:
    <npc>__ds-<technique>__base-<base>__gen-<gen>__train-<train>__eval-<judge>__p-<hash>__<timestamp>
    """
    ts = timestamp or artifact_timestamp()
    parts = [
        _slugify_npc_key(npc_key, 40),
        f"ds-{slugify_artifact_part(dataset_technique, 32)}",
        f"base-{slugify_artifact_part(base_model, 40)}",
        f"gen-{slugify_artifact_part(generation_preset, 32)}",
        f"train-{slugify_artifact_part(training_preset, 32)}",
        f"eval-{slugify_artifact_part(eval_model, 32)}",
        f"p-{params_hash(params)}",
        ts,
    ]
    artifact_id = "__".join(parts)
    if len(artifact_id) <= max_length:
        return artifact_id

    # Preserve npc, hash, timestamp. Trim variable middle parts.
    compact_parts = [
        _slugify_npc_key(npc_key, 32),
        f"ds-{slugify_artifact_part(dataset_technique, 20)}",
        f"base-{slugify_artifact_part(base_model, 28)}",
        f"gen-{slugify_artifact_part(generation_preset, 20)}",
        f"train-{slugify_artifact_part(training_preset, 20)}",
        f"eval-{slugify_artifact_part(eval_model, 20)}",
        f"p-{params_hash(params)}",
        ts,
    ]
    artifact_id = "__".join(compact_parts)
    if len(artifact_id) <= max_length:
        return artifact_id
    return artifact_id[: max_length - len(ts) - 2].rstrip("-_") + "__" + ts
