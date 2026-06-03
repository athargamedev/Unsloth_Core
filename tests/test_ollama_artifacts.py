from pathlib import Path

from src.core.dataset.ollama_artifacts import build_ollama_manifest, write_ollama_dataset_artifacts


def test_build_and_write_ollama_artifacts(tmp_path):
    spec = {"npc_name": "Test", "subject": "history", "dataset": {"examples_per_category": {"teaching": 1}}}
    examples = [{"messages": [], "metadata": {"category": "teaching", "concept": "x", "difficulty": "beginner"}}]
    manifest = build_ollama_manifest(
        npc_key="test_npc",
        technique="ollama",
        model="llama3.2:3b",
        spec_path=str(tmp_path / "spec.json"),
        spec=spec,
        examples=examples,
        train_examples=examples,
        val_examples=[],
        examples_per_category={"teaching": 1},
        generator_stats={"requests": 1},
        seed=42,
        temperature=0.6,
        multi_turn_ratio=0.25,
    )
    out = write_ollama_dataset_artifacts(output_path=tmp_path / "train.jsonl", train_examples=examples, val_examples=[], manifest=manifest, create_version_copy=False)
    assert Path(out["output_path"]).exists()
    assert out["val_path"] is None
    assert out["manifest_path"] is not None
    assert Path(out["manifest_path"]).exists()
    assert manifest["npc_key"] == "test_npc"
