from __future__ import annotations

"""Shared workflow context helpers for dataset generation, training, and eval.

This module centralizes the recurring resolution logic that used to be copied
across multiple scripts:
- load a subject spec
- infer npc_key
- resolve dataset technique from the spec or on-disk datasets
- resolve train/validation dataset paths
- resolve model and preset fallbacks

The goal is to keep generation, training, evaluation, and comparison aligned on
one consistent view of the active workflow for a chosen NPC/model.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import paths
from src.core.ops.model_presets import resolve_training_preset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_ID = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"


@dataclass(frozen=True)
class WorkflowContext:
    spec_path: Path | None
    spec: dict[str, Any]
    npc_key: str
    technique: str
    dataset_train_path: Path
    dataset_val_path: Path
    model_id: str
    preset: str | None

    @property
    def dataset_clean_path(self) -> Path:
        return self.dataset_train_path if self.dataset_train_path.name == "train_clean.jsonl" else self.dataset_train_path.with_name("train_clean.jsonl")

    @property
    def dataset_raw_path(self) -> Path:
        return self.dataset_train_path if self.dataset_train_path.name == "train.jsonl" else self.dataset_train_path.with_name("train.jsonl")

    @property
    def dataset_path(self) -> Path:
        return self.dataset_train_path

    @property
    def spec_text(self) -> str:
        return json.dumps(self.spec, indent=2, ensure_ascii=False)



def load_subject_spec(spec_path: str | Path) -> dict[str, Any]:
    file_path = Path(spec_path)
    if not file_path.is_absolute():
        file_path = (PROJECT_ROOT / file_path).resolve()
    with file_path.open(encoding="utf-8") as handle:
        spec = json.load(handle)
    if not isinstance(spec, dict):
        raise ValueError(f"Spec is not a JSON object: {file_path}")
    spec.setdefault("__path__", str(file_path))
    return spec



def infer_npc_key(spec: dict[str, Any], spec_path: str | Path | None = None) -> str:
    npc_key = str(spec.get("npc_key") or "").strip()
    if npc_key:
        return npc_key
    if spec_path is not None:
        return Path(spec_path).stem
    if spec.get("name"):
        return str(spec["name"]).strip().lower().replace(" ", "_")
    return "unknown"



def infer_spec_technique(spec: dict[str, Any]) -> str | None:
    technique = spec.get("technique") or spec.get("dataset", {}).get("technique")
    if technique is None:
        return None
    technique = str(technique).strip()
    return technique or None



def infer_model_id(spec: dict[str, Any], model_override: str | None = None) -> str:
    if model_override:
        return model_override
    return (
        spec.get("model")
        or spec.get("model_id")
        or spec.get("llm", {}).get("model_name")
        or spec.get("llm", {}).get("base_model")
        or DEFAULT_MODEL_ID
    )



def resolve_workflow_context(
    spec_path: str | Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    npc_key: str | None = None,
    technique: str | None = None,
    model_override: str | None = None,
    preset: str | None = None,
) -> WorkflowContext:
    loaded_spec = dict(spec or {})
    resolved_spec_path = Path(spec_path) if spec_path else None
    if not loaded_spec and resolved_spec_path is not None:
        loaded_spec = load_subject_spec(resolved_spec_path)

    resolved_npc_key = npc_key or infer_npc_key(loaded_spec, resolved_spec_path)
    preferred_technique = technique or infer_spec_technique(loaded_spec)
    resolved_technique, train_path, val_path = paths.resolve_dataset_context(resolved_npc_key, preferred_technique)

    if train_path.name != "train_clean.jsonl":
        clean_candidate = train_path.with_name("train_clean.jsonl")
        if clean_candidate.exists():
            train_path = clean_candidate

    resolved_model_id = infer_model_id(loaded_spec, model_override=model_override)
    spec_preset = loaded_spec.get("preset") or loaded_spec.get("training", {}).get("preset")
    resolved_preset = resolve_training_preset(resolved_model_id, preset=preset, spec_preset=spec_preset)

    return WorkflowContext(
        spec_path=resolved_spec_path,
        spec=loaded_spec,
        npc_key=resolved_npc_key,
        technique=resolved_technique,
        dataset_train_path=train_path,
        dataset_val_path=val_path,
        model_id=resolved_model_id,
        preset=resolved_preset,
    )
