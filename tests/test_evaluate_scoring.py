import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate import (
    compare_models,
    identity_prompt_requires_name,
    response_specificity_score,
)


def metrics(*, sentences_ok=True, name_ok=True, no_ai_disclaimer=True, length=20, quality=30, sentences=2):
    return {
        "sentences_ok": sentences_ok,
        "name_ok": name_ok,
        "no_ai_disclaimer": no_ai_disclaimer,
        "length": length,
        "quality": quality,
        "sentences": sentences,
        "has_think_tags": False,
    }


def test_identity_prompt_requires_name_only_for_self_introduction_questions():
    assert identity_prompt_requires_name("Who are you and what do you teach?") is True
    assert identity_prompt_requires_name("What is your name?") is True
    assert identity_prompt_requires_name("Can you help me understand cardio?") is False
    assert identity_prompt_requires_name("Explain the medieval period simply.") is False


def test_response_specificity_penalizes_generic_filler_and_rewards_domain_terms():
    spec = {
        "subject": "Astronomy and space science",
        "concepts": [{"name": "solar system"}, {"name": "telescopes"}],
        "system_prompt": "KNOWLEDGE: solar system, planets, telescopes, galaxies",
    }

    generic = "Great question. Once you understand this, everything falls into place naturally."
    specific = "Telescopes gather light so we can see faint planets, galaxies, and details in the solar system."

    assert response_specificity_score(specific, spec=spec) > response_specificity_score(generic, spec=spec)


def test_compare_models_specificity_breaks_tie_against_short_generic_candidate():
    spec = {
        "npc_name": "AstronomyGuide",
        "subject": "Astronomy and space science",
        "concepts": [{"name": "telescopes"}],
        "system_prompt": "KNOWLEDGE: telescopes, planets, galaxies, solar system",
    }
    baseline_results = [
        {
            "question": "Can you help me understand telescopes?",
            "response": "Telescopes collect more light than our eyes, which lets us see faint planets and galaxies more clearly.",
            "metrics": metrics(name_ok=False),
            "metadata": {"concept": "telescopes", "category": "teaching"},
            "expected": "Telescopes gather light and improve angular resolution for observing distant objects.",
        }
    ]
    candidate_results = [
        {
            "question": "Can you help me understand telescopes?",
            "response": "Great question. Once you grasp this concept, the rest falls into place.",
            "metrics": metrics(name_ok=False),
            "metadata": {"concept": "telescopes", "category": "teaching"},
            "expected": "Telescopes gather light and improve angular resolution for observing distant objects.",
        }
    ]

    result = compare_models(baseline_results, candidate_results, spec=spec, judge=None)

    assert result["baseline_wins"] == 1
    assert result["candidate_wins"] == 0
    assert result["comparisons"][0]["winner"] == "baseline"
