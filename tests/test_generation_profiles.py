from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dataset.generation_profiles import (
    DialogueGuardrail,
    _concept_anchor,
    _is_history_subject,
    _is_cooking_subject,
    _topic_to_anchor,
    generate_dialogue_response,
    generate_identity_response,
    generate_quest_response,
    generate_refusal_response,
    generate_teaching_response,
)


def history_spec():
    return {
        "npc_name": "HistoryGuide",
        "subject": "World history: ancient civilizations, classical antiquity, medieval period, Renaissance, modern era, world wars, historical thinking",
        "dialogue": {
            "max_sentences": 5,
            "max_characters": 500,
            "allow_formatting": False,
            "example_topics": ["What caused the fall of Rome?"],
        },
    }


def chef_spec():
    return {
        "npc_name": "ChefAssistant",
        "subject": "Cooking fundamentals: knife skills, heat, flavor, food safety, and kitchen workflow",
        "dialogue": {
            "max_sentences": 3,
            "max_characters": 200,
            "allow_formatting": False,
            "example_topics": ["How do I chop an onion safely?"],
        },
    }


def test_is_history_subject_detects_history_specs():
    assert _is_history_subject(history_spec())
    assert not _is_history_subject(chef_spec())


def test_history_core_timeline_anchor_is_domain_specific():
    anchor = _concept_anchor("core timeline anchors", history_spec())
    assert "placing events in order" in anchor.lower()


def test_history_primary_source_quest_mentions_citation():
    response = generate_quest_response(history_spec(), "core timeline anchors", scenario_name="primary_source")
    assert "cite one source" in response.lower()






def test_is_cooking_subject_detects_chef_specs():
    assert _is_cooking_subject(chef_spec())
    assert not _is_cooking_subject(history_spec())
def test_cooking_kitchen_organization_anchor_is_specific():
    anchor = _concept_anchor("kitchen organization", chef_spec())
    assert "clean station" in anchor.lower() or "workflow" in anchor.lower()


def test_cooking_teaching_mentions_safety_heat_and_texture(monkeypatch):
    monkeypatch.setattr("scripts.dataset.generation_profiles.random.choice", lambda seq: seq[0])
    response = generate_teaching_response(chef_spec(), "ingredient science")
    lowered = response.lower()
    assert "heat" in lowered
    assert "texture" in lowered
    assert "ingredient science" in lowered


def test_cooking_dialogue_mentions_result_change(monkeypatch):
    monkeypatch.setattr("scripts.dataset.generation_profiles.random.choice", lambda seq: seq[0])
    response = generate_dialogue_response(chef_spec(), "kitchen organization", dialogue_type="clarification")
    lowered = response.lower()
    assert "texture" in lowered or "safety" in lowered or "result" in lowered

def test_topic_to_anchor_strips_question_prefixes():
    assert _topic_to_anchor("What caused the fall of Rome?", "history") == "The fall of Rome"


def test_history_teaching_uses_source_date_and_consequence(monkeypatch):
    monkeypatch.setattr("scripts.dataset.generation_profiles.random.choice", lambda seq: seq[0])
    response = generate_teaching_response(history_spec(), "historical methodology")
    lowered = response.lower()
    assert "source" in lowered
    assert "date" in lowered
    assert "consequence" in lowered

def test_history_refusal_labels_speculation():
    response = generate_refusal_response(history_spec(), "Will not present speculation as fact")
    assert "speculation" in response.lower()


def test_refusal_templates_keep_explicit_boundary_and_redirect(monkeypatch):
    monkeypatch.setattr("scripts.dataset.generation_profiles.random.choice", lambda seq: seq[-1])

    for spec, boundary in [
        (history_spec(), "topic change request"),
        (history_spec(), "misinformation or conspiracy"),
        (chef_spec(), "medical or dietary"),
        (chef_spec(), "unsafe food preparation"),
        (chef_spec(), "generic boundary"),
    ]:
        response = generate_refusal_response(spec, boundary)
        lowered = response.lower()
        assert any(marker in lowered for marker in ["i can't", "i cannot", "i don't", "outside"])
        assert "instead" in lowered or "i can help with" in lowered


def test_guardrail_rejects_disclaimers_and_markdown():
    guardrail = DialogueGuardrail()

    ok, reason = guardrail.validate("As an AI, I cannot help with that.", [], history_spec())
    assert not ok
    assert "AI disclaimer" in reason

    ok, reason = guardrail.validate("## heading\n- item", [], history_spec())
    assert not ok
    assert "markdown" in reason.lower()
