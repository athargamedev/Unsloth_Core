"""P8.3 — Targeted row generation from component contracts.

When a component validation fails, generate dataset rows addressing
only that specific contract component.
"""

from __future__ import annotations

import pytest

from src.core.specs.components import (
    GroundingContract,
    IdentityContract,
    RefusalContract,
)
from src.core.specs.generation import generate_component_rows

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def identity() -> IdentityContract:
    return IdentityContract(
        npc_key="chef_assistant",
        personality="Calm, practical, encouraging",
        background="Seasoned kitchen guide",
        mannerisms="Step-by-step instructions",
        role="chef_assistant",
        archetype="mentor",
    )


@pytest.fixture
def refusal() -> RefusalContract:
    return RefusalContract(
        boundaries=[
            "Will not help with crash diets",
            "Will not recommend unsafe shortcuts",
        ],
        redirect_policy="Redirects to balanced meals and safe temperatures",
    )


@pytest.fixture
def grounding() -> GroundingContract:
    return GroundingContract(
        expertise=["knife skills", "cooking techniques", "food safety"],
        reference_doc="data/npcs/reference_docs/chef_assistant_primer.md",
        difficulty_levels=["beginner", "intermediate"],
    )


# ── Refusal → targeted refusal rows ──────────────────────────────────


class TestRefusalComponentRows:
    def test_refusal_contract_generates_refusal_rows(self, refusal: RefusalContract):
        rows = generate_component_rows("refusal", refusal, npc_key="chef_assistant")
        assert len(rows) >= 1
        for row in rows:
            assert row.category == "refusal"
            assert row.npc_key == "chef_assistant"
            assert row.user_prompt
            assert row.assistant_spec  # describes expected response shape

    def test_refusal_rows_map_boundaries(self, refusal: RefusalContract):
        rows = generate_component_rows("refusal", refusal, npc_key="chef_assistant")
        boundary_texts = [r.boundary_source for r in rows if r.boundary_source]
        # At least one row directly references each boundary
        for boundary in refusal.boundaries:
            assert any(boundary in rows[i].assistant_spec for i in range(len(rows))), (
                f"Boundary not covered: {boundary}"
            )

    def test_refusal_rows_include_redirect(self, refusal: RefusalContract):
        rows = generate_component_rows("refusal", refusal, npc_key="chef_assistant")
        assert any(refusal.redirect_policy[:20] in r.assistant_spec for r in rows)


# ── Identity → targeted identity rows ────────────────────────────────


class TestIdentityComponentRows:
    def test_identity_generates_identity_rows(self, identity: IdentityContract):
        rows = generate_component_rows("identity", identity, npc_key="chef_assistant")
        assert len(rows) >= 1
        for row in rows:
            assert row.category == "identity"
            assert row.npc_key == "chef_assistant"

    def test_identity_rows_include_personality(self, identity: IdentityContract):
        rows = generate_component_rows("identity", identity, npc_key="chef_assistant")
        assert any(identity.personality[:20] in r.assistant_spec for r in rows)

    def test_identity_rows_include_background(self, identity: IdentityContract):
        rows = generate_component_rows("identity", identity, npc_key="chef_assistant")
        assert any(identity.background[:20] in r.assistant_spec for r in rows)


# ── Grounding → targeted teaching rows ───────────────────────────────


class TestGroundingComponentRows:
    def test_grounding_generates_teaching_rows(self, grounding: GroundingContract):
        rows = generate_component_rows("grounding", grounding, npc_key="chef_assistant")
        assert len(rows) >= 1
        for row in rows:
            assert row.category == "teaching"
            assert row.npc_key == "chef_assistant"

    def test_grounding_rows_use_expertise_topics(self, grounding: GroundingContract):
        rows = generate_component_rows("grounding", grounding, npc_key="chef_assistant")
        # At least one row references each expertise area
        for expertise in grounding.expertise:
            found = False
            for r in rows:
                if expertise in r.assistant_spec or expertise in r.user_prompt:
                    found = True
                    break
            assert found, f"No row references expertise: {expertise}"


# ── Unknown component raises ─────────────────────────────────────────


class TestUnknownComponent:
    def test_unknown_component_raises(self):
        with pytest.raises(ValueError, match="unknown_component"):
            generate_component_rows("unknown_component", None, npc_key="test")
