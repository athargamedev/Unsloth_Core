#!/usr/bin/env python3
"""Resolve one canonical PipelineRunSpec before target execution.

The spec is intentionally plain JSON-serializable data.  It is the contract
between strategy profiles, workflow command building, target execution, report
bundles, and later dashboard rendering.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_NPCS = {"history_guide", "chef_assistant"}
PRODUCTION_PROFILES = {"npc-production-grounded", "npc-density-repair"}
DEFAULT_GENERATION_MODEL = "qwen2.5:7b"
DEFAULT_BASE_GGUF = ".models/llama-3.2-3b-instruct-q4_k_m.gguf"


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")


def _load_strategy_profile(profile: str) -> dict[str, Any]:
    path = PROJECT_ROOT / "etc" / "npc-production-strategy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = payload.get("profiles") or {}
    if profile not in profiles:
        raise ValueError(f"Unknown strategy profile: {profile}")
    return dict(profiles[profile] or {})


def _load_spec(npc_key: str, data_root: Path | None = None) -> dict[str, Any]:
    base = data_root or PROJECT_ROOT
    path = base / "data" / "npcs" / "specs" / f"{npc_key}.json"
    if not path.exists():
        raise ValueError(f"NPC spec not found: {path.relative_to(base)}")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class PipelineRunSpec:
    """Fully resolved target-run contract."""

    schema_version: str
    run_id: str
    npc_key: str
    profile: str
    target_stage: str
    technique: str
    production: bool
    active_npc: bool
    paths: dict[str, Any]
    generation: dict[str, Any]
    sanitize: dict[str, Any]
    dataset_eval: dict[str, Any]
    training: dict[str, Any]
    runtime_eval: dict[str, Any]
    integrations: dict[str, Any]
    gpu_policy: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)
    unavailable: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "npc_key": self.npc_key,
            "profile": self.profile,
            "target_stage": self.target_stage,
            "technique": self.technique,
            "production": self.production,
            "active_npc": self.active_npc,
            "paths": self.paths,
            "generation": self.generation,
            "sanitize": self.sanitize,
            "dataset_eval": self.dataset_eval,
            "training": self.training,
            "runtime_eval": self.runtime_eval,
            "integrations": self.integrations,
            "gpu_policy": self.gpu_policy,
            "overrides": self.overrides,
            "unavailable": self.unavailable,
        }

    def write_json(self, path: str | Path | None = None) -> Path:
        target = (
            Path(path)
            if path is not None
            else Path(self.paths["report_dir"]) / "pipeline_run_spec.json"
        )
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return target

    @property
    def spec_path(self) -> str:
        return str(self.paths["spec"])

    @property
    def reference_doc_path(self) -> str:
        return str(self.paths["reference_doc"])

    @property
    def dataset_dir(self) -> str:
        return str(self.paths["dataset_dir"])

    @property
    def raw_train_path(self) -> str:
        return str(self.paths["raw_train"])

    @property
    def clean_train_path(self) -> str:
        return str(self.paths["clean_train"])

    @property
    def adapter_gguf_path(self) -> str:
        return str(self.paths["adapter_gguf"])

    @property
    def quality_summary_path(self) -> str:
        return str(self.paths["quality_summary"])

    @property
    def feedback_json_path(self) -> str:
        return str(self.paths["feedback_json"])

    @property
    def base_gguf(self) -> str:
        return str(self.runtime_eval.get("baseline") or DEFAULT_BASE_GGUF)

    @property
    def generation_model(self) -> str:
        return str(self.generation.get("model") or DEFAULT_GENERATION_MODEL)

    @property
    def judge_model(self) -> str:
        return str(self.dataset_eval.get("judge_model") or "qwen2.5:7b")

    @property
    def dataset_eval_mode(self) -> str:
        return str(self.dataset_eval.get("mode") or "fast")

    @property
    def train_preset(self) -> str:
        return str(self.training.get("preset") or "fast-3b")


def resolve_pipeline_run_spec(
    *,
    npc_key: str,
    profile: str = "npc-production-grounded",
    technique: str | None = None,
    target_stage: str = "evaluate",
    report_dir: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
    data_root: str | Path | None = None,
) -> PipelineRunSpec:
    """Resolve strategy/spec/defaults into one JSON-serializable run spec."""

    strategy = _load_strategy_profile(profile)
    effective_technique = technique or str(strategy.get("technique") or "ollama")
    production = profile in PRODUCTION_PROFILES and not bool(
        strategy.get("dataset", {}).get("template_allowed")
    )
    active_npc = npc_key in ACTIVE_NPCS
    if production and not active_npc:
        raise ValueError(f"Inactive NPC cannot use production profile: {npc_key}")
    base = Path(data_root or PROJECT_ROOT)
    npc_spec = _load_spec(npc_key, data_root=base)

    run_id = _slug(f"{npc_key}_{profile}_{effective_technique}_{target_stage}")
    default_report_dir = Path("artifacts") / "reports" / npc_key / run_id
    report_path = Path(report_dir) if report_dir is not None else default_report_dir

    spec_path = Path("data") / "npcs" / "specs" / f"{npc_key}.json"
    reference_doc = npc_spec.get("reference_doc") or f"data/npcs/reference_docs/{npc_key}_primer.md"
    dataset_dir = Path("data") / "datasets" / npc_key / effective_technique
    adapter_gguf = Path("artifacts") / "exports" / npc_key / f"{npc_key}-lora-f16.gguf"
    feedback_json = Path("artifacts") / "eval" / "results" / "feedback" / f"{npc_key}.json"

    dataset_cfg = dict(strategy.get("dataset") or {})
    quality_gate = dict(strategy.get("quality_gate") or {})
    training = dict(strategy.get("training") or {})
    runtime_eval = dict(strategy.get("runtime_eval") or {})

    paths = {
        "spec": str(spec_path),
        "reference_doc": str(reference_doc),
        "dataset_dir": str(dataset_dir),
        "raw_train": str(dataset_dir / "train.jsonl"),
        "clean_train": str(dataset_dir / "train_clean.jsonl"),
        "quality_summary": str(dataset_dir / "quality_summary.json"),
        "quality_failures": str(dataset_dir / "quality_failures.json"),
        "quality_report": str(dataset_dir / "quality_report.json"),
        "adapter_gguf": str(adapter_gguf),
        "feedback_json": str(feedback_json),
        "report_dir": str(report_path),
        "pipeline_run_spec": str(report_path / "pipeline_run_spec.json"),
    }

    generation = {
        "command": "generate-ollama" if effective_technique == "ollama" else "generate",
        "model": DEFAULT_GENERATION_MODEL,
        "temperature": 0.6,
        "retry_policy": {"max_retries": 3},
        "batch_size": 4,
        "multi_turn_ratio": 0.25,
        "grounding_mode": "required" if dataset_cfg.get("require_grounding") else "optional",
        "fresh": True,
        "template_allowed": bool(dataset_cfg.get("template_allowed", False)),
        "target_total_rows": dataset_cfg.get("target_total_rows"),
        "category_targets": dataset_cfg.get("category_targets", {}),
        "density": dataset_cfg.get("density", {}),
    }
    sanitize = {
        "strict_canonical": True,
        "require_complete_metadata": True,
        "metadata_repair_policy": "block",
        "output": paths["clean_train"],
    }
    dataset_eval = {
        "mode": quality_gate.get("mode", "fast"),
        "cases_per_category": quality_gate.get("cases_per_category"),
        "judge_provider": quality_gate.get("judge_provider", "ollama"),
        "judge_model": quality_gate.get("judge_model") or "qwen2.5:7b",
        "confident": bool(quality_gate.get("confident", False)),
        "wandb": bool(quality_gate.get("wandb", False)),
        "disable_cache": bool(quality_gate.get("disable_cache", False)),
        "display": quality_gate.get("display", "all"),
        "ignore_errors": bool(quality_gate.get("ignore_errors", False)),
        "soft_fail": bool(quality_gate.get("soft_fail", False)),
        "output": paths["quality_summary"],
    }
    training_payload = {
        "preset": training.get("preset", "fast-3b"),
        "max_seq_len": training.get("max_seq_len"),
        "batch_size": training.get("batch_size"),
        "grad_accum": training.get("grad_accum"),
        "lora_r": training.get("lora_r"),
        "lora_alpha": training.get("lora_alpha"),
        "packing": training.get("packing"),
        "train_on_responses_only": bool(training.get("train_on_responses_only", False)),
        "export_gguf": bool(training.get("export_gguf", False)),
        "wandb": bool(training.get("wandb", False)),
        "gpu_lease_policy": "train_exclusive",
    }
    runtime_payload = {
        "baseline": runtime_eval.get("baseline") or DEFAULT_BASE_GGUF,
        "candidate_adapter": paths["adapter_gguf"],
        "requires_base_model": bool(runtime_eval.get("requires_base_model", True)),
        "base_model": runtime_eval.get("baseline") or DEFAULT_BASE_GGUF,
        "judge_provider": dataset_eval["judge_provider"],
        "judge_model": dataset_eval["judge_model"],
        "report_html": bool(runtime_eval.get("report_html", True)),
        "feedback_json": paths["feedback_json"],
        "wandb": bool(runtime_eval.get("wandb", False)),
        "candidate_win_rate_ready": runtime_eval.get("candidate_win_rate_ready"),
        "candidate_win_rate_inspect": runtime_eval.get("candidate_win_rate_inspect"),
    }
    integrations = {
        "deepeval": {"enabled": True, "required": production},
        "confident": {
            "enabled": bool(dataset_eval["confident"]),
            "required": bool(dataset_eval["confident"] and production),
        },
        "wandb": {
            "enabled": bool(
                dataset_eval["wandb"] or training_payload["wandb"] or runtime_payload["wandb"]
            ),
            "required": bool(
                production
                and (dataset_eval["wandb"] or training_payload["wandb"] or runtime_payload["wandb"])
            ),
        },
        "modal": {"enabled": False, "required": False},
    }
    gpu_policy = {
        "generate": {"lease_required": False, "lease_mode": "generation_shared"},
        "dataset_eval": {"lease_required": False, "lease_mode": "judge_shared"},
        "train": {"lease_required": True, "lease_mode": "train_exclusive"},
        "evaluate": {"lease_required": False, "lease_mode": "judge_shared"},
    }

    return PipelineRunSpec(
        schema_version="1.0",
        run_id=run_id,
        npc_key=npc_key,
        profile=profile,
        target_stage=target_stage,
        technique=effective_technique,
        production=production,
        active_npc=active_npc,
        paths=paths,
        generation=generation,
        sanitize=sanitize,
        dataset_eval=dataset_eval,
        training=training_payload,
        runtime_eval=runtime_payload,
        integrations=integrations,
        gpu_policy=gpu_policy,
        overrides=overrides or {},
        unavailable=[],
    )
