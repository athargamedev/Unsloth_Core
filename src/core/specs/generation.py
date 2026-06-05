#!/usr/bin/env python3
"""Targeted dataset row generation from component contracts.

When a component contract validation fails (e.g., insufficient refusal
boundaries), this module generates structured row specs for that
specific component only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.specs.components import (
    GroundingContract,
    IdentityContract,
    RefusalContract,
)


@dataclass(frozen=True)
class RowSpec:
    """A structured row spec ready for dataset generation."""

    npc_key: str
    category: str
    concept: str = ""
    user_prompt: str = ""
    assistant_spec: str = ""
    boundary_source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Refusal → targeted refusal rows ──────────────────────────────────


def _generate_refusal_rows(
    contract: RefusalContract,
    npc_key: str,
) -> list[RowSpec]:
    rows: list[RowSpec] = []
    for boundary in contract.boundaries:
        topic = _topic_from_boundary(boundary)
        rows.append(
            RowSpec(
                npc_key=npc_key,
                category="refusal",
                concept=_concept_from_boundary(boundary),
                user_prompt=f"Can you {topic}?",
                assistant_spec=(
                    f"Boundary: {boundary}. "
                    f"Redirect: {contract.redirect_policy}. "
                    "Provide a clear refusal followed by an in-scope alternative."
                ),
                boundary_source=boundary,
            )
        )
    # Generic redirect exercise
    rows.append(
        RowSpec(
            npc_key=npc_key,
            category="refusal",
            concept="redirect",
            user_prompt="I want something you can't help with.",
            assistant_spec=(
                f"Redirect policy: {contract.redirect_policy}. "
                "Refuse politely and offer an in-scope alternative."
            ),
            boundary_source="redirect_generic",
        )
    )
    return rows


def _topic_from_boundary(boundary: str) -> str:
    """Extract a brief topic from a refusal boundary statement."""
    boundary = boundary.replace("Will not ", "").replace("will not ", "")
    boundary = boundary.replace("Will not", "").replace("will not", "")
    return boundary.strip().strip(",").strip()


def _concept_from_boundary(boundary: str) -> str:
    """Derive a short concept key from a boundary."""
    boundary_lower = boundary.lower()
    if "diet" in boundary_lower or "eating" in boundary_lower:
        return "diet_refusal"
    if "unsafe" in boundary_lower or "shortcut" in boundary_lower:
        return "unsafe_shortcut"
    if "speculation" in boundary_lower or "misinformation" in boundary_lower:
        return "speculation_refusal"
    if "classified" in boundary_lower or "secret" in boundary_lower:
        return "classified_refusal"
    if "conspiracy" in boundary_lower:
        return "conspiracy_refusal"
    return "general_refusal"


# ── Identity → targeted identity rows ────────────────────────────────


def _generate_identity_rows(
    contract: IdentityContract,
    npc_key: str,
) -> list[RowSpec]:
    return [
        RowSpec(
            npc_key=npc_key,
            category="identity",
            concept="introduction",
            user_prompt="Who are you? Tell me about yourself.",
            assistant_spec=(
                f"Personality: {contract.personality}. "
                f"Background: {contract.background}. "
                f"Mannerisms: {contract.mannerisms}. "
                "Produce a concise 2-3 sentence self-introduction."
            ),
        ),
        RowSpec(
            npc_key=npc_key,
            category="identity",
            concept="role",
            user_prompt="What do you do?",
            assistant_spec=(
                f"Role: {contract.role}. "
                f"Mannerisms: {contract.mannerisms}. "
                "Describe your role and expertise in character."
            ),
        ),
    ]


# ── Grounding → targeted teaching rows ───────────────────────────────


def _generate_grounding_rows(
    contract: GroundingContract,
    npc_key: str,
) -> list[RowSpec]:
    rows: list[RowSpec] = []
    for expertise in contract.expertise:
        rows.append(
            RowSpec(
                npc_key=npc_key,
                category="teaching",
                concept=expertise,
                user_prompt=f"Can you explain {expertise}?",
                assistant_spec=(
                    f"Expertise: {expertise}. "
                    "Provide a clear, accurate explanation at a {difficulty} level."
                ),
            )
        )
    return rows


# ── Main dispatch ────────────────────────────────────────────────────


_COMPONENT_GENERATORS = {
    "refusal": _generate_refusal_rows,
    "identity": _generate_identity_rows,
    "grounding": _generate_grounding_rows,
}


def generate_component_rows(
    component: str,
    contract: RefusalContract | IdentityContract | GroundingContract | None,
    *,
    npc_key: str,
) -> list[RowSpec]:
    """Generate targeted dataset rows for a single component contract.

    Args:
        component: One of 'refusal', 'identity', 'grounding'.
        contract: The validated component contract.
        npc_key: NPC identifier.

    Returns:
        List of RowSpec objects for dataset generation.

    Raises:
        ValueError: If component is unknown.
    """
    generator = _COMPONENT_GENERATORS.get(component)
    if not generator:
        raise ValueError(
            f"Unknown component: {component}. Available: {list(_COMPONENT_GENERATORS.keys())}"
        )
    return generator(contract, npc_key)
