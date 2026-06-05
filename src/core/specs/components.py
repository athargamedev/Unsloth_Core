#!/usr/bin/env python3
"""Pydantic component contracts for NPC specs.

Each contract validates one dimension of an NPC specification,
making specs reusable/testable and targeted repair easier.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Constants ─────────────────────────────────────────────────────────

SUPPORTED_CATEGORIES = ("identity", "teaching", "dialogue", "quest", "refusal")
VALID_DIFFICULTY_LEVELS = frozenset({"beginner", "intermediate", "advanced"})
MIN_DATASET_EXAMPLES_PER_CATEGORY: dict[str, int] = {
    "identity": 8,
    "teaching": 32,
    "dialogue": 16,
    "quest": 8,
    "refusal": 8,
}


# ── IdentityContract ──────────────────────────────────────────────────


class IdentityContract(BaseModel, extra="ignore"):
    """Who the NPC is: personality, background, role, and mannerisms."""

    npc_key: str = Field(..., min_length=1, description="Canonical NPC identifier")
    personality: str = Field(..., min_length=1, description="Core personality traits")
    background: str = Field(..., min_length=1, description="NPC's background story")
    mannerisms: str = Field(..., min_length=1, description="Speech and behavior mannerisms")
    role: str = Field(default="", description="NPC's canonical role label")
    archetype: str = Field(default="", description="Character archetype (sage, mentor, etc.)")


# ── ToneContract ──────────────────────────────────────────────────────


class ToneContract(BaseModel, extra="ignore"):
    """Dialogue tone, style, and format rules."""

    conversation_style: str = Field(
        ..., min_length=1, description="Defined conversation style string"
    )
    max_sentences: int = Field(default=3, ge=1, le=20, description="Maximum sentences per response")
    max_characters: int = Field(
        ..., ge=1, le=5000, description="Maximum character count per response"
    )
    allow_formatting: bool = Field(
        default=False, description="Whether markdown formatting is allowed"
    )


# ── GroundingContract ─────────────────────────────────────────────────


class GroundingContract(BaseModel, extra="ignore"):
    """Subject matter expertise, reference doc, and difficulty levels."""

    expertise: list[str] = Field(..., min_length=1, description="List of expertise subjects")
    reference_doc: str = Field(default="", description="Path to reference primer markdown file")
    difficulty_levels: list[str] = Field(
        default_factory=lambda: ["beginner", "intermediate"],
        description="Allowed difficulty levels",
    )

    @field_validator("difficulty_levels")
    @classmethod
    def _validate_difficulty_levels(cls, v: list[str]) -> list[str]:
        unknown = set(v) - VALID_DIFFICULTY_LEVELS
        if unknown:
            raise ValueError(
                f"Unknown difficulty level(s): {unknown}. "
                f"Valid levels: {sorted(VALID_DIFFICULTY_LEVELS)}"
            )
        return v


# ── RefusalContract ───────────────────────────────────────────────────


class RefusalContract(BaseModel, extra="ignore"):
    """Defines what the NPC refuses to do and how it redirects."""

    boundaries: list[str] = Field(
        ..., min_length=1, description="List of refusal boundary statements"
    )
    redirect_policy: str = Field(
        ..., min_length=1, description="How the NPC redirects when refusing"
    )


# ── RuntimeConstraintContract ─────────────────────────────────────────


class RuntimeConstraintContract(BaseModel, extra="ignore"):
    """Runtime-exposed constraints for LLMUnity integration."""

    max_sentences: int = Field(default=3, ge=1, le=20, description="Max sentences per response")
    max_characters: int = Field(
        default=500, ge=1, le=5000, description="Max characters per response"
    )
    allow_formatting: bool = Field(default=False, description="Allow markdown formatting")


# ── DatasetDistributionContract ───────────────────────────────────────


class DatasetDistributionContract(BaseModel, extra="forbid"):
    """Per-category minimum example counts for dataset generation."""

    identity: int = Field(default=8, ge=0)
    teaching: int = Field(default=32, ge=0)
    dialogue: int = Field(default=16, ge=0)
    quest: int = Field(default=8, ge=0)
    refusal: int = Field(default=8, ge=0)

    def total_minimum(self) -> int:
        return self.identity + self.teaching + self.dialogue + self.quest + self.refusal


# ── NpcComponents composite ───────────────────────────────────────────


class NpcComponents(BaseModel):
    """Composite of all validated NPC component contracts."""

    identity: IdentityContract
    tone: ToneContract | None = None
    grounding: GroundingContract | None = None
    refusal: RefusalContract | None = None
    runtime: RuntimeConstraintContract | None = None
    distribution: DatasetDistributionContract | None = None


# ── Loader ────────────────────────────────────────────────────────────


def _str(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""


def load_npc_components(path: str | Path) -> NpcComponents:
    """Load and validate NPC components from an existing JSON spec file.

    Automatically extracts each component contract from the spec's
    current structure, filling defaults for any missing fields.
    """
    filepath = Path(path)
    raw = json.loads(filepath.read_text(encoding="utf-8"))

    # Identity
    identity_raw = raw.get("identity", {})
    if not isinstance(identity_raw, dict):
        identity_raw = {}
    identity = IdentityContract(
        npc_key=_str(raw.get("npc_key", "")),
        personality=_str(identity_raw.get("personality", "")),
        background=_str(identity_raw.get("background", "")),
        mannerisms=_str(identity_raw.get("mannerisms", "")),
        role=_str(raw.get("npc_key", "")),
    )

    # Tone (from dialogue section)
    dialogue_raw = raw.get("dialogue", {})
    if isinstance(dialogue_raw, dict):
        tone = ToneContract(
            conversation_style=_str(dialogue_raw.get("conversation_style", "")),
            max_sentences=dialogue_raw.get("max_sentences", 3),
            max_characters=dialogue_raw.get("max_characters", 500),
            allow_formatting=dialogue_raw.get("allow_formatting", False),
        )
    else:
        tone = ToneContract(conversation_style="", max_characters=500)

    # Grounding (from teaching section + subject + reference_doc)
    teaching_raw = raw.get("teaching", {})
    if isinstance(teaching_raw, dict):
        grounding = GroundingContract(
            expertise=teaching_raw.get("expertise", []),
            reference_doc=_str(raw.get("reference_doc", "")),
            difficulty_levels=teaching_raw.get("difficulty_levels", ["beginner", "intermediate"]),
        )
    else:
        grounding = None

    # Refusal
    refusal_raw = raw.get("refusal", {})
    if isinstance(refusal_raw, dict) and refusal_raw.get("boundaries"):
        refusal = RefusalContract(
            boundaries=refusal_raw["boundaries"],
            redirect_policy=_str(refusal_raw.get("redirect_policy", "")),
        )
    else:
        refusal = None

    # Runtime (from dialogue section)
    if isinstance(dialogue_raw, dict):
        runtime = RuntimeConstraintContract(
            max_sentences=dialogue_raw.get("max_sentences", 3),
            max_characters=dialogue_raw.get("max_characters", 500),
            allow_formatting=dialogue_raw.get("allow_formatting", False),
        )
    else:
        runtime = None

    # Distribution
    dataset_raw = raw.get("dataset", {})
    if isinstance(dataset_raw, dict):
        examples = dataset_raw.get("examples_per_category", {})
        if examples:
            distribution = DatasetDistributionContract(
                identity=examples.get("identity", 8),
                teaching=examples.get("teaching", 32),
                dialogue=examples.get("dialogue", 16),
                quest=examples.get("quest", 8),
                refusal=examples.get("refusal", 8),
            )
        else:
            distribution = DatasetDistributionContract()
    else:
        distribution = DatasetDistributionContract()

    return NpcComponents(
        identity=identity,
        tone=tone,
        grounding=grounding,
        refusal=refusal,
        runtime=runtime,
        distribution=distribution,
    )
