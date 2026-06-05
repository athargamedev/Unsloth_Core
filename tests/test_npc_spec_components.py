"""P8 — NPC Component Contracts: Pydantic models for spec contracts.

Tests:
- IdentityContract: validates personality, background, mannerisms, role
- ToneContract: validates conversation style, sentence/character limits, formatting rules
- GroundingContract: validates expertise subjects, reference doc path, difficulty levels
- RefusalContract: validates refusal boundaries, redirect policy
- RuntimeConstraintContract: validates max_sentences, max_characters, allow_formatting
- DatasetDistributionContract: validates per-category example counts
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

# RED: these imports fail until module exists
from src.core.specs.components import (
    DatasetDistributionContract,
    GroundingContract,
    IdentityContract,
    RefusalContract,
    RuntimeConstraintContract,
    ToneContract,
    load_npc_components,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def healthy_identity() -> dict:
    return {
        "npc_key": "history_guide",
        "personality": "Patient, clear, and curious",
        "background": "World history guide focused on major eras",
        "mannerisms": "Uses timelines and cause-effect comparisons",
        "role": "history_guide",
        "archetype": "sage",
    }


@pytest.fixture
def healthy_tone() -> dict:
    return {
        "conversation_style": "Detailed, vivid, chronological",
        "max_sentences": 5,
        "max_characters": 500,
        "allow_formatting": False,
    }


@pytest.fixture
def healthy_grounding() -> dict:
    return {
        "expertise": [
            "ancient civilizations",
            "classical antiquity",
            "medieval history",
            "modern history",
        ],
        "reference_doc": "data/npcs/reference_docs/history_guide_primer.md",
        "difficulty_levels": ["beginner", "intermediate", "advanced"],
    }


@pytest.fixture
def healthy_refusal() -> dict:
    return {
        "boundaries": [
            "Will not present speculation as fact",
            "Will not promote conspiracy theories",
        ],
        "redirect_policy": "Redirects to evidence and scholarly consensus",
    }


@pytest.fixture
def healthy_runtime() -> dict:
    return {
        "max_sentences": 3,
        "max_characters": 800,
        "allow_formatting": False,
    }


@pytest.fixture
def healthy_distribution() -> dict:
    return {
        "identity": 8,
        "teaching": 32,
        "dialogue": 16,
        "quest": 8,
        "refusal": 8,
    }


# ── IdentityContract ──────────────────────────────────────────────────


class TestIdentityContract:
    def test_healthy(self, healthy_identity):
        c = IdentityContract(**healthy_identity)
        assert c.npc_key == "history_guide"
        assert c.personality == "Patient, clear, and curious"
        assert c.role == "history_guide"
        assert c.archetype == "sage"

    def test_missing_npc_key_raises(self, healthy_identity):
        del healthy_identity["npc_key"]
        with pytest.raises(ValidationError, match="npc_key"):
            IdentityContract(**healthy_identity)

    def test_empty_personality_raises(self, healthy_identity):
        healthy_identity["personality"] = ""
        with pytest.raises(ValidationError, match="personality"):
            IdentityContract(**healthy_identity)

    def test_extra_fields_ignored(self):
        c = IdentityContract(
            npc_key="test",
            personality="A",
            background="B",
            mannerisms="C",
            role="test",
            archetype="test",
            unknown_field="ignored",
        )
        assert c.npc_key == "test"
        assert not hasattr(c, "unknown_field")


# ── ToneContract ──────────────────────────────────────────────────────


class TestToneContract:
    def test_healthy(self, healthy_tone):
        c = ToneContract(**healthy_tone)
        assert c.conversation_style == "Detailed, vivid, chronological"
        assert c.max_sentences == 5
        assert c.max_characters == 500
        assert c.allow_formatting is False

    def test_max_sentences_default(self):
        c = ToneContract(conversation_style="Direct", max_characters=300)
        assert c.max_sentences == 3  # default

    def test_max_characters_negative_raises(self, healthy_tone):
        healthy_tone["max_characters"] = -1
        with pytest.raises(ValidationError, match="max_characters"):
            ToneContract(**healthy_tone)

    def test_max_sentences_zero_raises(self, healthy_tone):
        healthy_tone["max_sentences"] = 0
        with pytest.raises(ValidationError):
            ToneContract(**healthy_tone)


# ── GroundingContract ─────────────────────────────────────────────────


class TestGroundingContract:
    def test_healthy(self, healthy_grounding):
        c = GroundingContract(**healthy_grounding)
        assert "ancient civilizations" in c.expertise
        assert c.reference_doc == "data/npcs/reference_docs/history_guide_primer.md"

    def test_empty_expertise_raises(self, healthy_grounding):
        healthy_grounding["expertise"] = []
        with pytest.raises(ValidationError, match="expertise"):
            GroundingContract(**healthy_grounding)

    def test_invalid_difficulty_level_raises(self, healthy_grounding):
        healthy_grounding["difficulty_levels"] = ["expert"]
        with pytest.raises(ValidationError):
            GroundingContract(**healthy_grounding)


# ── RefusalContract ───────────────────────────────────────────────────


class TestRefusalContract:
    def test_healthy(self, healthy_refusal):
        c = RefusalContract(**healthy_refusal)
        assert len(c.boundaries) == 2
        assert "Will not present speculation" in c.boundaries[0]

    def test_empty_boundaries_raises(self, healthy_refusal):
        healthy_refusal["boundaries"] = []
        with pytest.raises(ValidationError, match="boundaries"):
            RefusalContract(**healthy_refusal)

    def test_empty_redirect_policy_raises(self, healthy_refusal):
        healthy_refusal["redirect_policy"] = ""
        with pytest.raises(ValidationError, match="redirect_policy"):
            RefusalContract(**healthy_refusal)


# ── RuntimeConstraintContract ─────────────────────────────────────────


class TestRuntimeConstraintContract:
    def test_healthy(self, healthy_runtime):
        c = RuntimeConstraintContract(**healthy_runtime)
        assert c.max_sentences == 3
        assert c.max_characters == 800

    def test_allow_formatting_default(self):
        c = RuntimeConstraintContract(max_sentences=3, max_characters=800)
        assert c.allow_formatting is False

    def test_caps_must_be_positive(self):
        with pytest.raises(ValidationError):
            RuntimeConstraintContract(max_sentences=-1, max_characters=0)


# ── DatasetDistributionContract ───────────────────────────────────────


class TestDatasetDistributionContract:
    def test_healthy(self, healthy_distribution):
        c = DatasetDistributionContract(**healthy_distribution)
        assert c.identity == 8
        assert c.teaching == 32
        assert c.total_minimum() == 8 + 32 + 16 + 8 + 8

    def test_category_out_of_bounds_raises(self, healthy_distribution):
        healthy_distribution["teaching"] = -1
        with pytest.raises(ValidationError):
            DatasetDistributionContract(**healthy_distribution)

    def test_unknown_category_raises(self):
        with pytest.raises(ValidationError, match="Extra inputs"):
            DatasetDistributionContract(identity=5, extra_category=99)

    def test_missing_existing_field_defaults(self):
        """Partial dicts fill missing fields with repo defaults."""
        c = DatasetDistributionContract(identity=5)
        assert c.identity == 5
        assert c.teaching == 32  # default from contract


# ── load_npc_components ──────────────────────────────────────────────


class TestLoadNpcComponents:
    def test_loads_history_guide(self):
        path = Path("data/npcs/specs/history_guide.json")
        if not path.exists():
            pytest.skip("history_guide spec not available in test env")
        components = load_npc_components(path)
        assert components.identity.npc_key == "history_guide"
        assert components.grounding is not None
        assert components.refusal is not None
        assert components.tone is not None
        assert components.runtime is not None
