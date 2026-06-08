from src.core.runtime.response_shape import (
    apply_runtime_sentence_guard,
    count_sentences,
    spec_max_sentences,
    trim_to_max_sentences,
)


def test_runtime_sentence_guard_trims_to_spec_cap_and_tracks_raw_count():
    spec = {"dialogue": {"max_sentences": 3}}
    raw = "Keep hot food hot. Cool leftovers fast. Refrigerate within two hours. Reheat until steaming."

    shaped, meta = apply_runtime_sentence_guard(raw, spec=spec)

    assert shaped == "Keep hot food hot. Cool leftovers fast. Refrigerate within two hours."
    assert count_sentences(shaped) == 3
    assert meta["runtime_guard_applied"] is True
    assert meta["runtime_guard_raw_sentences"] == 4
    assert meta["runtime_guard_sentences"] == 3
    assert meta["runtime_guard_max_sentences"] == 3


def test_runtime_sentence_guard_preserves_abbreviations():
    text = "Dr. Smith says chill rice fast. U.S.A. food rules vary by state. Label leftovers. Extra sentence."

    assert spec_max_sentences({"dialogue": {"max_sentences": 2}}) == 2
    assert trim_to_max_sentences(text, 2) == (
        "Dr. Smith says chill rice fast. U.S.A. food rules vary by state."
    )
