import json
from pathlib import Path

from src.core.ops.confident_goldens import (
    build_confident_artifacts,
    project_chatml_rows_to_confident,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_projects_single_turn_chatml_to_confident_golden_without_actual_output(tmp_path):
    spec_path = tmp_path / "chef_assistant.json"
    ref_path = tmp_path / "chef_primer.md"
    spec_path.write_text(
        json.dumps({"npc_key": "chef_assistant", "reference_doc": str(ref_path)}), encoding="utf-8"
    )
    ref_path.write_text(
        "# Chef\n\n## Evaluation Contract\nStay safe.\n\n## Concepts\nFood safety facts.",
        encoding="utf-8",
    )
    dataset_path = (
        tmp_path / "data" / "datasets" / "chef_assistant" / "ollama" / "train_clean.jsonl"
    )
    row = {
        "messages": [
            {"role": "system", "content": "Chef system prompt"},
            {"role": "user", "content": "Is pink chicken safe?"},
            {"role": "assistant", "content": "Cook chicken to 165°F."},
        ],
        "metadata": {
            "npc_key": "chef_assistant",
            "category": "teaching",
            "technique": "ollama",
            "source": "ollama:OllamaGenerator",
            "split": "train",
            "concept": "food safety",
            "difficulty": "beginner",
            "content_hash": "abc123",
            "generator_params": {"temperature": 0.6, "seed": 42},
        },
    }
    _write_jsonl(dataset_path, [row])

    artifacts = project_chatml_rows_to_confident(dataset_path, spec_path=spec_path)

    assert len(artifacts.single_turn_goldens) == 1
    assert artifacts.conversational_goldens == []
    golden = artifacts.single_turn_goldens[0]
    assert golden["input"] == "Is pink chicken safe?"
    assert golden["expectedOutput"] == "Cook chicken to 165°F."
    assert "actualOutput" not in golden
    assert golden["sourceFile"].endswith("train_clean.jsonl")
    assert golden["customColumnKeyValues"]["turn_type"] == "single"
    assert golden["customColumnKeyValues"]["quality_status"] == "candidate"
    assert golden["additionalMetadata"]["system_prompt_hash"]
    assert golden["additionalMetadata"]["reference_doc_hash"]
    assert golden["context"]


def test_projects_multi_turn_chatml_to_conversational_golden(tmp_path):
    dataset_path = (
        tmp_path / "data" / "datasets" / "chef_assistant" / "ollama" / "train_clean.jsonl"
    )
    row = {
        "messages": [
            {"role": "system", "content": "Chef system prompt"},
            {"role": "user", "content": "Remember I avoid peanuts."},
            {"role": "assistant", "content": "I’ll remember no peanuts."},
            {"role": "user", "content": "What sauce can I make?"},
            {"role": "assistant", "content": "Use yogurt sauce and avoid peanut sauces."},
        ],
        "metadata": {
            "npc_key": "chef_assistant",
            "category": "dialogue",
            "technique": "ollama",
            "concept": "memory retention",
            "difficulty": "intermediate",
            "content_hash": "def456",
            "generator_params": {"multi_turn": True},
        },
    }
    _write_jsonl(dataset_path, [row])

    artifacts = project_chatml_rows_to_confident(dataset_path)

    assert artifacts.single_turn_goldens == []
    assert len(artifacts.conversational_goldens) == 1
    golden = artifacts.conversational_goldens[0]
    assert golden["scenario"] == "memory retention"
    assert golden["expectedOutcome"]
    assert golden["turns"] == [
        {"role": "user", "content": "Remember I avoid peanuts."},
        {"role": "assistant", "content": "I’ll remember no peanuts."},
        {"role": "user", "content": "What sauce can I make?"},
        {"role": "assistant", "content": "Use yogurt sauce and avoid peanut sauces."},
    ]
    assert golden["customColumnKeyValues"]["turn_type"] == "conversational"
    assert golden["customColumnKeyValues"]["metric_focus"] == "knowledge_retention"


def test_build_confident_artifacts_writes_split_files_and_manifest(tmp_path):
    dataset_path = (
        tmp_path / "data" / "datasets" / "chef_assistant" / "ollama" / "train_clean.jsonl"
    )
    rows = [
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "Q"},
                {"role": "assistant", "content": "A"},
            ],
            "metadata": {"npc_key": "chef_assistant", "technique": "ollama", "content_hash": "h1"},
        },
        {
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "Remember X"},
                {"role": "assistant", "content": "OK"},
                {"role": "user", "content": "Use it"},
                {"role": "assistant", "content": "Using X"},
            ],
            "metadata": {"npc_key": "chef_assistant", "technique": "ollama", "content_hash": "h2"},
        },
    ]
    _write_jsonl(dataset_path, rows)

    manifest = build_confident_artifacts(dataset_path)

    confident_dir = dataset_path.parent / "confident"
    assert (confident_dir / "single_turn_goldens.jsonl").exists()
    assert (confident_dir / "conversational_goldens.jsonl").exists()
    assert (confident_dir / "push_manifest.json").exists()
    assert manifest["counts"] == {"single_turn": 1, "conversational": 1}
    assert manifest["aliases"]["single_turn"] == "ucore-chef-assistant-ollama-single-v1"
    assert manifest["aliases"]["conversational"] == "ucore-chef-assistant-ollama-conversation-v1"
