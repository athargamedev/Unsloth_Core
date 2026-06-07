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
from typing import Any

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


def _section(ctx: Any, name: str) -> dict[str, Any]:
    return getattr(ctx, name, {}) if not isinstance(ctx, dict) else ctx.get(name, {})


def _bool_flag(value: Any) -> bool:
    return bool(value)


def build_stage_command(ctx: Any, stage: str) -> list[str]:
    """Return the real top-level ``./ucore`` command for a workflow stage.

    ``ctx`` may be the legacy ``WorkflowContext`` or the newer
    ``PipelineRunSpec``.  The latter carries all effective strategy/profile
    flags, while the former preserves older unit-test and compatibility defaults.
    """

    generation = _section(ctx, "generation")
    dataset_eval = _section(ctx, "dataset_eval")
    training = _section(ctx, "training")
    runtime_eval = _section(ctx, "runtime_eval")
    sanitize = _section(ctx, "sanitize")
    technique = getattr(ctx, "technique", DEFAULT_TECHNIQUE)

    if stage == "generate":
        command_name = generation.get("command", "generate-ollama" if technique == "ollama" else "generate")
        if command_name == "generate-ollama":
            cmd = [
                "./ucore",
                "generate-ollama",
                ctx.spec_path,
                "--model",
                str(generation.get("model", ctx.generation_model)),
            ]
            if generation.get("temperature") is not None and generation:
                cmd.extend(["--temperature", str(generation["temperature"])])
            if generation.get("batch_size") is not None and generation:
                cmd.extend(["--batch-size", str(generation["batch_size"])])
            if generation.get("retry_policy", {}).get("max_retries") is not None:
                cmd.extend(["--max-retries", str(generation["retry_policy"]["max_retries"])])
            if generation.get("multi_turn_ratio") is not None and generation:
                cmd.extend(["--multi-turn-ratio", str(generation["multi_turn_ratio"])])
            if generation.get("fresh", True):
                cmd.append("--fresh")
            return cmd
        return ["./ucore", "generate", ctx.spec_path, "--technique", technique]

    if stage == "sanitize":
        cmd = [
            "./ucore",
            "sanitize",
            ctx.raw_train_path,
            "--output",
            str(sanitize.get("output", ctx.clean_train_path)),
        ]
        if hasattr(ctx, "spec_path") and sanitize:
            cmd.extend(["--spec", ctx.spec_path])
        if sanitize.get("strict_canonical", True):
            cmd.append("--strict-canonical")
        if sanitize.get("require_complete_metadata", True):
            cmd.append("--require-complete-metadata")
        return cmd

    if stage == "dataset_eval":
        cmd = [
            "./ucore",
            "dataset-eval",
            ctx.spec_path,
            "--technique",
            technique,
            "--mode",
            str(dataset_eval.get("mode", ctx.dataset_eval_mode)),
        ]
        if dataset_eval.get("cases_per_category") is not None:
            cmd.extend(["--cases-per-category", str(dataset_eval["cases_per_category"])])
        if dataset_eval.get("judge_provider"):
            cmd.extend(["--judge-provider", str(dataset_eval["judge_provider"])])
        cmd.extend(["--judge-model", str(dataset_eval.get("judge_model", ctx.judge_model))])
        if dataset_eval.get("display"):
            cmd.extend(["--display", str(dataset_eval["display"])])
        if dataset_eval.get("ignore_errors"):
            cmd.append("--ignore-errors")
        if dataset_eval.get("soft_fail"):
            cmd.append("--soft-fail")
        if dataset_eval.get("wandb"):
            cmd.append("--wandb")
        if dataset_eval.get("confident"):
            cmd.append("--confident")
        cmd.extend(["--output", str(dataset_eval.get("output", ctx.quality_summary_path))])
        return cmd

    if stage == "train":
        cmd = [
            "./ucore",
            "train",
            ctx.spec_path,
            "--technique",
            technique,
            "--preset",
            str(training.get("preset", ctx.train_preset)),
        ]
        optional_flags = [
            ("max_seq_len", "--max-seq-len"),
            ("batch_size", "--batch-size"),
            ("grad_accum", "--grad-accum"),
            ("lora_r", "--lora-r"),
            ("lora_alpha", "--lora-alpha"),
        ]
        for key, flag in optional_flags:
            if training.get(key) is not None:
                cmd.extend([flag, str(training[key])])
        if training.get("packing") is not None:
            cmd.extend(["--packing", str(training["packing"]).lower()])
        if training.get("train_on_responses_only") is not None and training:
            cmd.extend(["--train-on-responses", str(training["train_on_responses_only"]).lower()])
        if training.get("wandb"):
            cmd.append("--wandb")
        if training.get("export_gguf", True):
            cmd.append("--export-gguf")
        return cmd

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
        cmd = [
            "./ucore",
            "evaluate",
            "--baseline",
            str(runtime_eval.get("baseline", ctx.base_gguf)),
            "--candidate",
            str(runtime_eval.get("candidate_adapter", ctx.adapter_gguf_path)),
        ]
        if runtime_eval.get("requires_base_model", True):
            cmd.extend(["--base-model", str(runtime_eval.get("base_model", ctx.base_gguf))])
        cmd.extend([
            "--spec",
            ctx.spec_path,
            "--feedback-json",
            str(runtime_eval.get("feedback_json", ctx.feedback_json_path)),
        ])
        if runtime_eval.get("report_html", True):
            cmd.append("--report-html")
        cmd.append("--judge")
        if runtime_eval.get("judge_provider"):
            cmd.extend(["--judge-provider", str(runtime_eval["judge_provider"])])
        cmd.extend(["--judge-model", str(runtime_eval.get("judge_model", ctx.judge_model))])
        if runtime_eval.get("wandb"):
            cmd.append("--wandb")
        return cmd

    raise ValueError(f"Unknown workflow stage: {stage}")


def validate_workflow_stage(stage: str) -> None:
    if stage not in CANONICAL_WORKFLOW_STAGES:
        raise ValueError(f"Unknown workflow stage: {stage}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
