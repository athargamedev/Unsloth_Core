"""P8.2 — Migration adapter tests: existing JSON specs load through components.

Verifies:
- All existing NPC spec JSONs load through load_npc_components() without error.
- Existing validate_spec() still works unchanged.
- Components validation matches or extends existing spec validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.dataset.validate_subject_spec import validate_spec
from src.core.specs.components import (
    load_npc_components,
)

SPEC_DIR = Path("data/npcs/specs")

# ── Find all known specs ──────────────────────────────────────────────

KNOWN_SPECS = sorted(SPEC_DIR.glob("*.json")) if SPEC_DIR.exists() else []
SPEC_NAMES = [s.stem for s in KNOWN_SPECS]


def test_known_specs_exist():
    """Guard: at least one spec exists in the known directory."""
    assert KNOWN_SPECS, f"No .json specs found in {SPEC_DIR}"


# ── Migration tests ───────────────────────────────────────────────────


class TestMigrationAdapter:
    """All existing specs load through component models without error."""

    @pytest.mark.parametrize("spec_path", KNOWN_SPECS, ids=SPEC_NAMES)
    def test_load_npc_components(self, spec_path: Path):
        components = load_npc_components(spec_path)
        assert components.identity is not None
        assert components.identity.npc_key == spec_path.stem
        # Each spec must at minimum have identity + tone
        assert components.tone is not None
        assert components.tone.max_sentences >= 1

    @pytest.mark.parametrize("spec_path", KNOWN_SPECS, ids=SPEC_NAMES)
    def test_component_value_integrity(self, spec_path: Path):
        """Component fields match the source JSON document fields."""
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        components = load_npc_components(spec_path)

        # Identity fields match
        raw_identity = raw.get("identity", {})
        assert components.identity.personality == raw_identity.get("personality", "")
        assert components.identity.background == raw_identity.get("background", "")
        assert components.identity.mannerisms == raw_identity.get("mannerisms", "")

        # Dialogue limits match
        raw_dialogue = raw.get("dialogue", {})
        if raw_dialogue:
            assert components.tone.max_sentences == raw_dialogue.get("max_sentences", 3)
            assert components.tone.max_characters == raw_dialogue.get("max_characters", 500)

            if components.runtime:
                assert components.runtime.max_sentences == raw_dialogue.get("max_sentences", 3)

        # Refusal boundaries match
        raw_refusal = raw.get("refusal", {})
        if raw_refusal and raw_refusal.get("boundaries"):
            assert components.refusal is not None
            assert len(components.refusal.boundaries) == len(raw_refusal["boundaries"])


# ── Existing validation still works ───────────────────────────────────


class TestExistingSpecValidation:
    """Existing validate_spec() still passes for all specs."""

    @pytest.mark.parametrize("spec_path", KNOWN_SPECS, ids=SPEC_NAMES)
    def test_validate_spec_passes(self, spec_path: Path):
        result = validate_spec(spec_path)
        assert result.status != "error", f"{spec_path.name}: {result.errors}"


# ── Round-trip: validate_spec enriched by components ──────────────────


class TestComponentEnhancedValidation:
    """Components enhance validation without breaking backward compat."""

    @pytest.mark.parametrize("spec_path", KNOWN_SPECS, ids=SPEC_NAMES)
    def test_components_have_contract_coverage(self, spec_path: Path):
        """Every existing spec section has a corresponding component."""
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
        components = load_npc_components(spec_path)

        # identity -> IdentityContract
        if "identity" in raw:
            assert components.identity is not None

        # teaching -> GroundingContract
        if "teaching" in raw:
            assert components.grounding is not None

        # refusal -> RefusalContract
        if "refusal" in raw:
            assert components.refusal is not None

        # dialogue -> ToneContract + RuntimeConstraintContract
        if "dialogue" in raw:
            assert components.tone is not None
            assert components.runtime is not None

        # No spec should lose data in round-trip
        if components.refusal:
            assert len(components.refusal.boundaries) >= 1
