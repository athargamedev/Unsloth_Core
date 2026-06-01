#!/usr/bin/env python3
"""Canonical pipeline DAG and prerequisite audit helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.ops.artifact_registry import ArtifactRegistry

CANONICAL_STAGE_ORDER = ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate"]

STAGE_OUTPUT_ARTIFACTS = {
    "generate": ["dataset_raw"],
    "sanitize": ["dataset_clean"],
    "dataset_eval": ["quality_summary"],
    "train": ["adapter_checkpoint"],
    "export": ["gguf_adapter"],
    "evaluate": ["eval_index"],
}

STAGE_REQUIRED_ARTIFACTS = {
    "generate": [],
    "sanitize": ["dataset_raw"],
    "dataset_eval": ["dataset_clean"],
    "train": ["dataset_clean", "quality_summary"],
    "export": ["adapter_checkpoint"],
    "evaluate": ["gguf_adapter"],
}


@dataclass(frozen=True)
class StageValidation:
    stage: str
    ok: bool
    missing_stages: list[str]
    missing_artifacts: list[str]
    next_required_stage: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "ok": self.ok,
            "missing_stages": self.missing_stages,
            "missing_artifacts": self.missing_artifacts,
            "next_required_stage": self.next_required_stage,
        }


class PipelineDAG:
    """Validates stage order and artifact prerequisites using ArtifactRegistry."""

    def __init__(self, registry: ArtifactRegistry | None = None) -> None:
        self.registry = registry or ArtifactRegistry()

    def validate_stage(self, stage: str, *, npc_key: str, technique: str | None = None) -> StageValidation:
        self._assert_known_stage(stage)
        required = STAGE_REQUIRED_ARTIFACTS[stage]
        missing_artifacts = [
            artifact_type
            for artifact_type in required
            if self.registry.latest_artifact(npc_key, artifact_type, technique=technique) is None
        ]
        missing_stages = [self._producer_for(artifact_type) for artifact_type in missing_artifacts]
        missing_stages = [s for s in missing_stages if s]
        next_required_stage = self._next_required_stage(stage, npc_key=npc_key, technique=technique)
        return StageValidation(
            stage=stage,
            ok=not missing_artifacts,
            missing_stages=missing_stages,
            missing_artifacts=missing_artifacts,
            next_required_stage=next_required_stage,
        )

    def plan_to_stage(self, target_stage: str, *, npc_key: str, technique: str | None = None) -> dict[str, Any]:
        self._assert_known_stage(target_stage)
        target_index = CANONICAL_STAGE_ORDER.index(target_stage)
        steps = []
        for stage in CANONICAL_STAGE_ORDER[: target_index + 1]:
            validation = self.validate_stage(stage, npc_key=npc_key, technique=technique)
            steps.append(
                {
                    "stage": stage,
                    "ready": validation.ok,
                    "missing_artifacts": validation.missing_artifacts,
                    "missing_stages": validation.missing_stages,
                    "produces": STAGE_OUTPUT_ARTIFACTS.get(stage, []),
                }
            )
        return {
            "npc_key": npc_key,
            "technique": technique,
            "target_stage": target_stage,
            "ready": all(step["ready"] for step in steps),
            "steps": steps,
        }

    def write_plan(self, path: str | Path, target_stage: str, *, npc_key: str, technique: str | None = None) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.plan_to_stage(target_stage, npc_key=npc_key, technique=technique), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return output

    def _next_required_stage(self, target_stage: str, *, npc_key: str, technique: str | None = None) -> str | None:
        target_index = CANONICAL_STAGE_ORDER.index(target_stage)
        for stage in CANONICAL_STAGE_ORDER[:target_index]:
            for artifact_type in STAGE_OUTPUT_ARTIFACTS.get(stage, []):
                if self.registry.latest_artifact(npc_key, artifact_type, technique=technique) is None:
                    return stage
        return None

    @staticmethod
    def _producer_for(artifact_type: str) -> str | None:
        for stage, outputs in STAGE_OUTPUT_ARTIFACTS.items():
            if artifact_type in outputs:
                return stage
        return None

    @staticmethod
    def _assert_known_stage(stage: str) -> None:
        if stage not in CANONICAL_STAGE_ORDER:
            raise ValueError(f"Unknown pipeline stage: {stage}")
