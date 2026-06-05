#!/usr/bin/env python3
"""Canonical pipeline DAG, target cache planning, and prerequisite audit helpers."""

from __future__ import annotations

import hashlib
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

TECHNIQUE_SCOPED_ARTIFACTS = {
    "dataset_raw",
    "dataset_clean",
    "quality_summary",
    "adapter_checkpoint",
}


def stage_input_signature(stage: str, input_records: list[dict[str, Any]]) -> str:
    """Return a stable content signature for a stage's current inputs.

    The signature keys on artifact type + content hash, not run_id, so a
    re-recorded artifact with identical bytes remains cache-equivalent while a
    changed upstream file invalidates downstream stages.
    """
    payload = {
        "stage": stage,
        "inputs": [
            {
                "artifact_type": record.get("artifact_type"),
                "sha256": record.get("sha256"),
                "path": record.get("path") if record.get("sha256") is None else None,
            }
            for record in input_records
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


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

    def validate_stage(
        self, stage: str, *, npc_key: str, technique: str | None = None
    ) -> StageValidation:
        self._assert_known_stage(stage)
        required = STAGE_REQUIRED_ARTIFACTS[stage]
        missing_artifacts = [
            artifact_type
            for artifact_type in required
            if self.registry.latest_artifact(
                npc_key,
                artifact_type,
                technique=technique if artifact_type in TECHNIQUE_SCOPED_ARTIFACTS else None,
            )
            is None
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

    def plan_to_stage(
        self, target_stage: str, *, npc_key: str, technique: str | None = None
    ) -> dict[str, Any]:
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

    def plan_target(
        self, target_stage: str, *, npc_key: str, technique: str | None = None
    ) -> dict[str, Any]:
        """Plan whether the target artifact chain is cached, stale, or missing.

        Unlike :meth:`plan_to_stage`, which answers "can this stage run?", this
        answers "is the target already achieved?" and marks stages as:
        - cached: output exists and its stored input_signature matches current inputs
        - stale: output exists but current upstream signatures changed
        - missing: output does not exist
        - blocked: required input artifacts are absent
        """
        self._assert_known_stage(target_stage)
        target_index = CANONICAL_STAGE_ORDER.index(target_stage)
        steps: list[dict[str, Any]] = []

        for stage in CANONICAL_STAGE_ORDER[: target_index + 1]:
            required_types = STAGE_REQUIRED_ARTIFACTS[stage]
            input_records: list[dict[str, Any]] = []
            missing_inputs: list[str] = []
            for artifact_type in required_types:
                record = self._latest_for_artifact(npc_key, artifact_type, technique=technique)
                if record is None:
                    missing_inputs.append(artifact_type)
                else:
                    input_records.append(record)

            output_types = STAGE_OUTPUT_ARTIFACTS.get(stage, [])
            output_records = [
                self._latest_for_artifact(npc_key, artifact_type, technique=technique)
                for artifact_type in output_types
            ]
            missing_outputs = [
                artifact_type
                for artifact_type, record in zip(output_types, output_records, strict=False)
                if record is None
            ]
            concrete_outputs = [record for record in output_records if record is not None]
            current_signature = stage_input_signature(stage, input_records)

            if missing_inputs:
                status = "blocked"
                action = "wait"
                reason = "missing_inputs"
            elif missing_outputs:
                status = "missing"
                action = "run"
                reason = "output_missing"
            elif required_types and any(
                "input_signature" not in (record.get("metadata") or {})
                for record in concrete_outputs
            ):
                status = "inconclusive"
                action = "run"
                reason = "lineage_missing"
            elif required_types and any(
                (record.get("metadata") or {}).get("input_signature") != current_signature
                for record in concrete_outputs
            ):
                status = "stale"
                action = "run"
                reason = "input_signature_changed"
            else:
                status = "cached"
                action = "skip"
                reason = "cache_hit"

            steps.append(
                {
                    "stage": stage,
                    "status": status,
                    "action": action,
                    "reason": reason,
                    "input_signature": current_signature,
                    "requires": required_types,
                    "produces": output_types,
                    "missing_inputs": missing_inputs,
                    "missing_outputs": missing_outputs,
                    "outputs": concrete_outputs,
                }
            )

        return {
            "npc_key": npc_key,
            "technique": technique,
            "target_stage": target_stage,
            "ready": all(step["status"] == "cached" for step in steps),
            "steps": steps,
            "blockers": self._compute_blockers(steps, npc_key=npc_key, technique=technique),
            "cache_hits": self._compute_cache_hits(steps),
            "gpu_policy": self._compute_gpu_policy(target_stage),
            "next_required_stage": self._next_required_stage(
                target_stage, npc_key=npc_key, technique=technique
            ),
        }

    @staticmethod
    def _compute_blockers(
        steps: list[dict[str, Any]],
        *,
        npc_key: str,
        technique: str | None,
    ) -> list[str]:
        blockers: list[str] = []
        for step in steps:
            if step["status"] == "blocked":
                inputs = step.get("missing_inputs") or []
                for artifact in inputs:
                    blockers.append(f"{step['stage']}: missing input '{artifact}'")
            elif step["status"] == "stale":
                blockers.append(f"{step['stage']}: upstream inputs changed, needs rerun")
        return blockers

    @staticmethod
    def _compute_cache_hits(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        hits: dict[str, dict[str, Any]] = {}
        for step in steps:
            if step["status"] == "cached" and step.get("outputs"):
                outputs = step["outputs"]
                if outputs:
                    hits[step["stage"]] = {
                        "artifact_type": outputs[0].get("artifact_type"),
                        "sha256": outputs[0].get("sha256"),
                        "run_id": outputs[0].get("run_id"),
                    }
        return hits

    @staticmethod
    def _compute_gpu_policy(target_stage: str) -> dict[str, dict[str, bool | str]]:
        policy: dict[str, dict[str, bool | str]] = {}
        target_idx = CANONICAL_STAGE_ORDER.index(target_stage)
        for stage in CANONICAL_STAGE_ORDER[: target_idx + 1]:
            if stage == "train":
                policy[stage] = {
                    "lease_required": True,
                    "lease_mode": "train_exclusive",
                    "reason": "Training requires exclusive GPU access",
                }
            elif stage in ("export", "evaluate"):
                policy[stage] = {
                    "lease_required": True,
                    "lease_mode": "judge_shared",
                    "reason": f"{stage.capitalize()} runs judge inference",
                }
            else:
                policy[stage] = {
                    "lease_required": False,
                    "lease_mode": None,
                    "reason": "No GPU lease needed",
                }
        return policy

    def write_plan(
        self, path: str | Path, target_stage: str, *, npc_key: str, technique: str | None = None
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                self.plan_to_stage(target_stage, npc_key=npc_key, technique=technique),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return output

    def _next_required_stage(
        self, target_stage: str, *, npc_key: str, technique: str | None = None
    ) -> str | None:
        target_index = CANONICAL_STAGE_ORDER.index(target_stage)
        for stage in CANONICAL_STAGE_ORDER[:target_index]:
            for artifact_type in STAGE_OUTPUT_ARTIFACTS.get(stage, []):
                if (
                    self.registry.latest_artifact(
                        npc_key,
                        artifact_type,
                        technique=technique
                        if artifact_type in TECHNIQUE_SCOPED_ARTIFACTS
                        else None,
                    )
                    is None
                ):
                    return stage
        return None

    def _latest_for_artifact(
        self, npc_key: str, artifact_type: str, *, technique: str | None = None
    ) -> dict[str, Any] | None:
        return self.registry.latest_artifact(
            npc_key,
            artifact_type,
            technique=technique if artifact_type in TECHNIQUE_SCOPED_ARTIFACTS else None,
        )

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
