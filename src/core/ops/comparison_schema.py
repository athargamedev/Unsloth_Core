#!/usr/bin/env python3
"""Pydantic schemas for model comparison runs — the canonical shape for all eval comparisons.

Every model-vs-model comparison across the NPC pipeline produces a ComparisonRun record.
This is written to Supabase eval_sessions, logged to W&B, and archived locally.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def make_comparison_id(
    npc_key: str,
    baseline_model: str,
    candidate_model: str,
    sequence_number: int = 1,
) -> str:
    """Generate a human-readable comparison ID.

    Format: {YYYYMMDD}_{npc_key}_{baseline}-vs-{candidate}_{seq:03d}

    Inverse of parse_comparison_id().
    """
    today = datetime.now(UTC).strftime("%Y%m%d")
    safe_baseline = baseline_model.replace(":", "-").replace("/", "-")
    safe_candidate = candidate_model.replace(":", "-").replace("/", "-")
    return f"{today}_{npc_key}_{safe_baseline}-vs-{safe_candidate}_{sequence_number:03d}"


class ComparisonRun(BaseModel):
    """Immutable record of a single model-vs-model comparison run.

    Stored in Supabase eval_sessions table and archived locally under
    .pipeline/compare/{comparison_id}/.
    """

    comparison_id: str = Field(
        description="Human-readable unique ID, e.g. '20260604_marvel_heroes_instructor_qwen-vs-llama_001'"
    )
    npc_key: str = Field(description="NPC identifier, e.g. 'marvel_heroes_instructor'")
    baseline_model: str = Field(description="Name of the baseline model, e.g. 'qwen2.5:7b'")
    candidate_model: str = Field(description="Name of the candidate model, e.g. 'llama3.1:8b'")
    judge_model: str = Field(
        default="qwen2.5:7b",
        description="Judge model used for evaluation",
    )
    dataset_path: str | None = Field(
        default=None,
        description="Path to the shared comparison dataset JSONL",
    )
    dataset_hash: str | None = Field(
        default=None,
        description="SHA256 hex digest of the comparison dataset content",
    )
    rows_evaluated: int = Field(default=0, ge=0, description="Number of rows evaluated")

    # Win/loss counts
    baseline_wins: int = Field(
        default=0, ge=0, description="Rows where baseline output was preferred"
    )
    candidate_wins: int = Field(
        default=0, ge=0, description="Rows where candidate output was preferred"
    )
    ties: int = Field(default=0, ge=0, description="Rows where judge called it a tie")
    win_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Candidate win rate (candidate_wins / rows_evaluated)",
    )

    # Structured breakdowns
    per_concept: dict[str, float] = Field(
        default_factory=dict,
        description="Win rate per concept, e.g. {'teaching': 0.8, 'dialogue': 0.6}",
    )
    weak_concepts: list[str] = Field(
        default_factory=list,
        description="Concepts where candidate win_rate < 0.5",
    )

    # Back-references
    baseline_eval_run_id: str | None = Field(
        default=None,
        description="RunRegistry ID for the baseline evaluation",
    )
    candidate_eval_run_id: str | None = Field(
        default=None,
        description="RunRegistry ID for the candidate evaluation",
    )

    # Artifacts produced
    feedback_json_path: str | None = Field(
        default=None, description="Path to the structured feedback JSON"
    )
    report_html_path: str | None = Field(default=None, description="Path to the HTML report")

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_iso_now, description="ISO 8601 UTC timestamp")

    # ── Post-init computed fields ─────────────────────────────────────

    def model_post_init(self, __context: Any) -> None:
        """Auto-compute win_rate and weak_concepts after field initialization."""
        if self.win_rate is None and self.rows_evaluated > 0:
            self.win_rate = self.candidate_wins / self.rows_evaluated
        if not self.weak_concepts and self.per_concept:
            self.weak_concepts = sorted(c for c, wr in self.per_concept.items() if wr < 0.5)

    @field_validator("win_rate")
    @classmethod
    def _ensure_win_rate_range(cls, v: float | None) -> float | None:
        """Clamp win_rate to [0.0, 1.0] if set."""
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError(f"win_rate must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("weak_concepts")
    @classmethod
    def _dedupe_weak_concepts(cls, v: list[str]) -> list[str]:
        """Remove duplicates from weak_concepts."""
        return list(dict.fromkeys(v)) if v else []

    def to_supabase(self) -> dict[str, Any]:
        """Convert to a dict suitable for Supabase eval_sessions row.

        Note: 'npc_key' is NOT included — it should be passed as a
        keyword argument to PipelineDB.create_eval_session().
        """
        data = self.model_dump()
        data.pop("npc_key", None)
        data.pop("comparison_id", None)  # re-include only if you want comparison_id in the row
        data.pop("created_at", None)  # DB auto-sets NOW()
        data["total_examples"] = data.pop("rows_evaluated", 0)
        return data

    @classmethod
    def from_feedback_json(
        cls,
        path: str | Path,
        npc_key: str,
        baseline_model: str,
        candidate_model: str,
        **overrides: Any,
    ) -> ComparisonRun:
        """Build a ComparisonRun from a structured feedback JSON file.

        Expected JSON shape:
        {
            "total_examples": int,
            "baseline_wins": int,
            "candidate_wins": int,
            "ties": int,
            "win_rate": float,
            "per_concept": {"concept": win_rate, ...},
            "weak_concepts": ["concept", ...],
            ...
        }
        """
        import json

        path = Path(path)
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        dataset_info = overrides.pop("dataset_info", {})

        return cls(
            comparison_id=make_comparison_id(
                npc_key=npc_key,
                baseline_model=baseline_model,
                candidate_model=candidate_model,
            ),
            npc_key=npc_key,
            baseline_model=baseline_model,
            candidate_model=candidate_model,
            rows_evaluated=data.get("total_examples", 0),
            baseline_wins=data.get("baseline_wins", 0),
            candidate_wins=data.get("candidate_wins", 0),
            ties=data.get("ties", 0),
            win_rate=data.get("win_rate"),
            per_concept=data.get("per_concept", {}),
            weak_concepts=data.get("weak_concepts", []),
            baseline_eval_run_id=data.get("baseline_eval_run_id"),
            candidate_eval_run_id=data.get("candidate_eval_run_id"),
            feedback_json_path=str(path),
            report_html_path=data.get("report_html_path"),
            metadata={
                **dataset_info,
                **overrides,
            },
            **{k: v for k, v in overrides.items() if k in cls.model_fields},
        )


def parse_comparison_id(comparison_id: str) -> dict[str, str]:
    """Reverse a comparison_id into its components.

    Input:  '20260604_marvel_heroes_instructor_qwen-vs-llama_001'
    Output: {'date': '20260604', 'npc': 'marvel_heroes_instructor',
             'baseline': 'qwen', 'candidate': 'llama', 'seq': '001'}
    """
    parts = comparison_id.split("_")
    if len(parts) < 4:
        raise ValueError(f"Invalid comparison_id: {comparison_id}")
    date = parts[0]
    seq = parts[-1]
    vs_part = parts[-2]  # e.g. "qwen-vs-llama"
    if "-vs-" not in vs_part:
        raise ValueError(f"Expected '-vs-' in comparison_id: {comparison_id}")
    baseline, candidate = vs_part.split("-vs-")
    npc_key = "_".join(parts[1:-2])
    return {"date": date, "npc": npc_key, "baseline": baseline, "candidate": candidate, "seq": seq}
