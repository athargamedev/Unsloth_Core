import json
from pathlib import Path

from src.core.ops.confident_classifiers import build_classifier_setup, write_classifier_setup
from src.core.dataset.confident_goldens import project_chatml_rows_to_confident


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_classifier_setup_contains_manual_ui_specs_and_agent_plan(tmp_path):
    setup = build_classifier_setup()

    names = [item["name"] for item in setup["trace_classifiers"]]
    assert "NPC Dataset Failure Mode" in names
    assert "NPC Dataset Strength" in names
    assert "NPC Repair Priority" in names
    assert setup["trace_settings"]["sample_rate_dev"] == 1.0
    assert setup["agent_required_for_classifiers"] is False
    assert setup["confident_agent_future"]["compose_file"] == "infra/confident-agent/compose.yaml"

    failure_mode = next(item for item in setup["trace_classifiers"] if item["name"] == "NPC Dataset Failure Mode")
    labels = {label["name"] for label in failure_mode["labels"]}
    assert "Vague / Low Specificity" in labels
    assert "Safety Boundary Weakness" in labels


def test_write_classifier_setup_writes_json_and_markdown(tmp_path):
    json_path = tmp_path / "classifiers.json"
    md_path = tmp_path / "classifiers.md"

    written = write_classifier_setup(json_path=json_path, markdown_path=md_path)

    assert written["json"] == json_path
    assert written["markdown"] == md_path
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["manual_setup_required"] is True
    text = md_path.read_text(encoding="utf-8")
    assert "NPC Dataset Failure Mode" in text
    assert "Confident Agent is not required for classifiers" in text


def test_projected_goldens_include_classifier_hints(tmp_path):
    dataset = tmp_path / "train_clean.jsonl"
    rows = [
        {
            "messages": [
                {"role": "system", "content": "You are HistoryGuide. Keep answers short."},
                {"role": "user", "content": "What makes classical antiquity fascinating?"},
                {"role": "assistant", "content": "It shaped civilization in many ways."},
            ],
            "metadata": {
                "npc_key": "history_guide",
                "category": "dialogue",
                "concept": "classical antiquity",
                "difficulty": "beginner",
                "technique": "ollama",
                "quality_score": 74,
            },
        },
        {
            "messages": [
                {"role": "system", "content": "You are Chef."},
                {"role": "user", "content": "Remember I avoid peanuts."},
                {"role": "assistant", "content": "I will remember you avoid peanuts."},
                {"role": "user", "content": "Suggest a snack."},
                {"role": "assistant", "content": "Try yogurt with berries, no peanuts."},
            ],
            "metadata": {
                "npc_key": "chef_assistant",
                "category": "dialogue",
                "concept": "memory preference",
                "difficulty": "beginner",
                "technique": "ollama",
            },
        },
    ]
    _write_jsonl(dataset, rows)

    artifacts = project_chatml_rows_to_confident(dataset)

    single_cols = artifacts.single_turn_goldens[0]["customColumnKeyValues"]
    assert single_cols["classifier_expected_failure_mode"] == "Vague / Low Specificity"
    assert single_cols["classifier_repair_priority"] == "P1 Training Harmful"
    assert single_cols["classifier_strength_hint"] == "Needs Review"

    conv_cols = artifacts.conversational_goldens[0]["customColumnKeyValues"]
    assert conv_cols["classifier_metric_focus"] == "knowledge_retention"
    assert conv_cols["classifier_conversation_weakness_hint"] == "Lost Context"
    assert conv_cols["classifier_expected_strength"] == "Good Memory Use"
