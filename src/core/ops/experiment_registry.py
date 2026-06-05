"""Pydantic models for experiment registry — models, datasets, metrics.

These are the canonical shapes for Unsloth_Core's experiment tracking
backed by Supabase tables (model_registry, dataset_versions, metric_collections).

Usage:
    from src.core.ops.experiment_registry import ModelRegistryEntry, register_model

    entry = ModelRegistryEntry(
        model_name="chef_assistant_qwen2.5_lora_r16",
        npc_key="chef_assistant",
        base_model="qwen2.5:7b",
        technique="lora",
    )
    created = register_model(entry)
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ═══════════════════════════════════════════════════════════════
# 1. MODEL REGISTRY
# ═══════════════════════════════════════════════════════════════


class ModelRegistryEntry(BaseModel):
    """A single model (adapter/GGUF) produced by the training pipeline.

    Maps to the `model_registry` Supabase table.
    """

    model_name: str = Field(
        ...,
        description="Human-readable name, e.g. 'chef_assistant_qwen2.5_lora_r16'",
        pattern=r"^[a-z0-9_\-\.]+$",
    )
    npc_key: str
    base_model: str
    technique: str = Field(..., pattern=r"^(lora|qlora|full)$")

    # Lineage (optional at creation)
    training_run_id: str | None = None
    dataset_hash: str | None = None
    parent_model_id: str | None = None

    # Config snapshots
    lora_config: dict[str, Any] = Field(default_factory=dict)
    training_params: dict[str, Any] = Field(default_factory=dict)

    # Evaluation results (populated after comparison)
    win_rate: float | None = None
    eval_session_id: str | None = None
    quality_gate_pass_rate: float | None = None

    # Artifact links
    adapter_artifact_id: str | None = None
    gguf_artifact_id: str | None = None
    gguf_quantization: str | None = None

    # Status & metadata
    status: str = Field(
        default="draft", pattern=r"^(draft|training|ready|deployed|archived|failed)$"
    )
    tags: list[str] = Field(default_factory=list)

    deployed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _ensure_gguf_quant(self) -> ModelRegistryEntry:
        """If gguf_artifact_id is set, gguf_quantization should also be set."""
        if self.gguf_artifact_id and not self.gguf_quantization:
            self.gguf_quantization = "q4_k_m"  # sensible default
        return self

    def to_supabase(self) -> dict[str, Any]:
        """Convert to dict for Supabase INSERT, dropping None values."""
        data = self.model_dump(exclude_none=True)
        for field in ("created_at", "updated_at", "deployed_at"):
            if field in data and isinstance(data[field], datetime):
                data[field] = data[field].isoformat()
        return data


# ═══════════════════════════════════════════════════════════════
# 2. DATASET VERSIONS
# ═══════════════════════════════════════════════════════════════


class DatasetVersion(BaseModel):
    """A versioned snapshot of a dataset's content and provenance.

    Maps to the `dataset_versions` Supabase table.
    """

    npc_key: str
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    content_hash: str = ""  # auto-computed if empty
    technique: str
    row_count: int = 0
    size_bytes: int = 0
    split_info: dict[str, int] = Field(default_factory=dict)
    concept_coverage: dict[str, int] = Field(default_factory=dict)

    parent_hash: str | None = None
    parent_id: str | None = None
    generation_params: dict[str, Any] = Field(default_factory=dict)
    change_log: str | None = None

    quality_gate_pass_rate: float | None = None
    quality_gate_id: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _auto_hash(self) -> DatasetVersion:
        """Auto-compute content_hash from change_log + generation_params if empty."""
        if not self.content_hash:
            raw = json.dumps(
                {
                    "npc_key": self.npc_key,
                    "technique": self.technique,
                    "change_log": self.change_log,
                    "generation_params": self.generation_params,
                    "row_count": self.row_count,
                },
                sort_keys=True,
                default=str,
            )
            self.content_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return self

    def to_supabase(self) -> dict[str, Any]:
        """Convert to dict for Supabase INSERT."""
        data = self.model_dump(exclude_none=True)
        for field in ("created_at", "updated_at"):
            if field in data and isinstance(data[field], datetime):
                data[field] = data[field].isoformat()
        return data

    @classmethod
    def from_dataset_file(
        cls,
        path: str | Path,
        npc_key: str,
        technique: str,
        generation_params: dict[str, Any] | None = None,
    ) -> DatasetVersion:
        """Create a DatasetVersion from an existing dataset file."""
        p = Path(path)
        content = p.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()

        row_count = 0
        if p.suffix == ".jsonl":
            row_count = sum(1 for _ in p.open(encoding="utf-8") if _.strip())

        return cls(
            npc_key=npc_key,
            technique=technique,
            content_hash=content_hash,
            row_count=row_count,
            size_bytes=p.stat().st_size,
            generation_params=generation_params or {},
            change_log=f"Snapshot from {p.name}",
        )


# ═══════════════════════════════════════════════════════════════
# 3. METRIC COLLECTIONS
# ═══════════════════════════════════════════════════════════════


class MetricCollection(BaseModel):
    """Training metrics at a single step.

    Maps to the `metric_collections` Supabase table.
    """

    run_id: str
    npc_key: str
    step: int = Field(..., ge=0)

    # Optional linkages
    job_id: str | None = None
    model_registry_id: str | None = None

    # Step metadata
    epoch: float | None = None

    # Core metrics
    loss: float | None = None
    grad_norm: float | None = None
    learning_rate: float | None = None
    tokens_per_second: float | None = None
    gpu_memory_mb: float | None = None
    gpu_utilization: float | None = None

    # Catch-all for non-standard metrics
    extra_metrics: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime | None = None

    def to_supabase(self) -> dict[str, Any]:
        """Convert to dict for Supabase INSERT, dropping None values."""
        data = self.model_dump(exclude_none=True)
        if "created_at" in data and isinstance(data["created_at"], datetime):
            data["created_at"] = data["created_at"].isoformat()
        return data


# ═══════════════════════════════════════════════════════════════
# SHARED NAMING HELPERS
# ═══════════════════════════════════════════════════════════════


def make_model_name(npc_key: str, base_model: str, technique: str, rank: int | None = None) -> str:
    """Generate a canonical model name.

    >>> make_model_name("chef_assistant", "qwen2.5:7b", "lora", rank=16)
    'chef_assistant_qwen2.5-7b_lora_r16'
    """
    base = base_model.replace(":", "-").replace("/", "-").replace(".", "-")
    name = f"{npc_key}_{base}_{technique}"
    if rank is not None:
        name += f"_r{rank}"
    return name


# ═══════════════════════════════════════════════════════════════
# 4. CANONICAL EXPERIMENT RUNS (P6)
# ═══════════════════════════════════════════════════════════════


class ExperimentRun(BaseModel):
    """Canonical local/Supabase-safe experiment record.

    This intentionally unifies local canonical bundles, W&B run ids,
    Confident traces, quality gates, comparisons, and promotion evidence into
    one append-only record shape. It is safe to mirror to external systems but
    also works offline as JSONL.
    """

    schema_version: str = "experiment_run/v1"
    run_id: str
    npc_key: str
    stage: str
    technique: str = "unknown"
    status: str = Field(
        default="complete", pattern=r"^(queued|running|complete|failed|error|skipped)$"
    )
    profile: str | None = None

    dataset_hash: str | None = None
    model_name: str | None = None
    base_model: str | None = None

    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] = Field(default_factory=dict)
    external_refs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        """Serialize for JSONL/Supabase-style storage."""
        data = self.model_dump(exclude_none=True)
        for field in ("created_at", "updated_at"):
            if field in data and isinstance(data[field], datetime):
                data[field] = data[field].isoformat()
        return data

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ExperimentRun:
        return cls(**record)


class ExperimentRegistry:
    """Append-only JSONL experiment registry.

    This is the local/offline source of truth for P6. PipelineDB/W&B/Confident
    can mirror or enrich these records, but promotion logic should read records
    here instead of guessing from latest artifact pointers.
    """

    DEFAULT_PATH = Path(".pipeline") / "experiments.jsonl"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else self.DEFAULT_PATH

    def record_run(self, run: ExperimentRun) -> dict[str, Any]:
        record = run.to_record()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, default=str)
            f.write("\n")
        return record

    def iter_runs(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def query_runs(
        self,
        *,
        npc_key: str | None = None,
        stage: str | None = None,
        run_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.iter_runs()
        if npc_key is not None:
            rows = [r for r in rows if r.get("npc_key") == npc_key]
        if stage is not None:
            rows = [r for r in rows if r.get("stage") == stage]
        if run_id is not None:
            rows = [r for r in rows if r.get("run_id") == run_id]
        if status is not None:
            rows = [r for r in rows if r.get("status") == status]
        if limit is not None:
            rows = rows[-limit:]
        return rows

    def latest_comparison_for_candidate(
        self,
        *,
        npc_key: str,
        candidate_run_id: str,
    ) -> dict[str, Any] | None:
        comparisons = self.query_runs(npc_key=npc_key, stage="compare", status="complete")
        for row in reversed(comparisons):
            comparison = row.get("comparison") or {}
            if comparison.get("candidate_run_id") == candidate_run_id:
                return row
        return None
