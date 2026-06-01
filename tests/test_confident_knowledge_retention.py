import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def test_confident_metric_collections_include_knowledge_retention_for_conversations():
    from src.core.dataset.dataset_eval import _build_conversational_metric_collection

    collection = _build_conversational_metric_collection()

    assert collection["name"] == "npc-conversation-quality"
    assert "knowledge_retention" in collection["include"]
    assert "role_adherence" in collection["include"]
    assert "conversation_completeness" in collection["include"]


def test_remote_case_conversion_splits_single_and_multi_turn_rows(tmp_path):
    from src.core.dataset.dataset_eval import _convert_test_cases_for_remote

    jsonl = tmp_path / "train_clean.jsonl"
    rows = [
        {
            "messages": [
                {"role": "system", "content": "You are history_guide."},
                {"role": "user", "content": "Who are you?"},
                {"role": "assistant", "content": "I guide history with primary sources."},
            ],
            "metadata": {"npc_key": "history_guide", "category": "identity", "concept": "anchor"},
        },
        {
            "messages": [
                {"role": "system", "content": "You are chef_assistant."},
                {"role": "user", "content": "Remember I am allergic to peanuts."},
                {"role": "assistant", "content": "I will avoid peanuts."},
                {"role": "user", "content": "Suggest a snack."},
                {"role": "assistant", "content": "Try apple slices with yogurt, no peanuts."},
            ],
            "metadata": {"npc_key": "chef_assistant", "category": "dialogue", "concept": "allergy memory"},
        },
    ]
    jsonl.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    single_turn, conversational = _convert_test_cases_for_remote(jsonl)

    assert len(single_turn) == 1
    assert single_turn[0]["input"] == "Who are you?"
    assert len(conversational) == 1
    assert conversational[0]["name"] == "chef_assistant:dialogue:allergy memory"
    assert conversational[0]["turns"] == [
        {"role": "user", "content": "Remember I am allergic to peanuts."},
        {"role": "assistant", "content": "I will avoid peanuts."},
        {"role": "user", "content": "Suggest a snack."},
        {"role": "assistant", "content": "Try apple slices with yogurt, no peanuts."},
    ]
    assert conversational[0]["additionalMetadata"]["knowledge_retention_target"] == "user-provided facts across turns"
