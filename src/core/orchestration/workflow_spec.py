#!/usr/bin/env python3
"""Canonical Unsloth_Core workflow command specification.

This module is the single source of truth for commands emitted by
``./ucore target plan/run``.  It intentionally emits real top-level
``./ucore`` commands, not pseudo command groups, so dry-runs are copy/pasteable
and agents have one reliable sequence to follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CANONICAL_WORKFLOW_STAGES: tuple[str, ...] = (
    "generate",
    "sanitize",
    "dataset_eval",
    "train",
    "export",
    "evaluate",
)

DEFAULT_TECHNIQUE = "ollama"
DEFAULT_GENERATION_MODEL = "qwen2.5:7b"
DEFAULT_JUDGE_MODEL = "qwen2.5:7b"
DEFAULT_DATASET_EVAL_MODE = "fast"
DEFAULT_TRAIN_PRESET = "fast-3b"
DEFAULT_BASE_GGUF = (
    "/home/athar/Setup Guide In-Editor Tutorial/Assets/StreamingAssets/Models/"
    "llama-3.2-3b-instruct-q4_k_m.gguf"
)


@dataclass(frozen=True)
class WorkflowContext:
    """Inputs needed to materialize a canonical stage command."""

    npc_key: str
    technique: str = DEFAULT_TECHNIQUE
    profile: str = "npc-production-grounded"
    generation_model: str = DEFAULT_GENERATION_MODEL
    judge_model: str = DEFAULT_JUDGE_MODEL
    dataset_eval_mode: str = DEFAULT_DATASET_EVAL_MODE
    train_preset: str = DEFAULT_TRAIN_PRESET
    base_gguf: str = DEFAULT_BASE_GGUF

    @property
    def spec_path(self) -> str:
        return f"data/npcs/specs/{self.npc_key}.json"

    @property
    def dataset_dir(self) -> str:
        return f"data/datasets/{self.npc_key}/{self.technique}"

    @property
    def raw_train_path(self) -> str:
        return f"{self.dataset_dir}/train.jsonl"

    @property
    def clean_train_path(self) -> str:
        return f"{self.dataset_dir}/train_clean.jsonl"

    @property
    def adapter_gguf_path(self) -> str:
        return f"artifacts/exports/{self.npc_key}/{self.npc_key}-lora-f16.gguf"

    @property
    def quality_summary_path(self) -> str:
        return f"{self.dataset_dir}/quality_summary.json"

    @property
    def feedback_json_path(self) -> str:
        return f"artifacts/eval/results/feedback/{self.npc_key}.json"


def build_stage_command(ctx: WorkflowContext, stage: str) -> list[str]:
    """Return the real top-level ``./ucore`` command for a workflow stage."""

    if stage == "generate":
        return [
            "./ucore",
            "generate-ollama",
            ctx.spec_path,
            "--model",
            ctx.generation_model,
            "--fresh",
        ]

    if stage == "sanitize":
        return [
            "./ucore",
            "sanitize",
            ctx.raw_train_path,
            "--output",
            ctx.clean_train_path,
            "--strict-canonical",
            "--require-complete-metadata",
        ]

    if stage == "dataset_eval":
        return [
            "./ucore",
            "dataset-eval",
            ctx.spec_path,
            "--technique",
            ctx.technique,
            "--mode",
            ctx.dataset_eval_mode,
            "--judge-model",
            ctx.judge_model,
            "--output",
            ctx.quality_summary_path,
        ]

    if stage == "train":
        return [
            "./ucore",
            "train",
            ctx.spec_path,
            "--technique",
            ctx.technique,
            "--preset",
            ctx.train_preset,
            "--export-gguf",
        ]

    if stage == "export":
        return [
            "./ucore",
            "export",
            ctx.npc_key,
            "--outtype",
            "f16",
            "--resume",
        ]

    if stage == "evaluate":
        return [
            "./ucore",
            "evaluate",
            "--baseline",
            ctx.base_gguf,
            "--candidate",
            ctx.adapter_gguf_path,
            "--base-model",
            ctx.base_gguf,
            "--spec",
            ctx.spec_path,
            "--feedback-json",
            ctx.feedback_json_path,
            "--report-html",
            "--judge",
            "--judge-model",
            ctx.judge_model,
        ]

    raise ValueError(f"Unknown workflow stage: {stage}")


def validate_workflow_stage(stage: str) -> None:
    if stage not in CANONICAL_WORKFLOW_STAGES:
        raise ValueError(f"Unknown workflow stage: {stage}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
