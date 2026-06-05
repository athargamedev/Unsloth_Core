from src.core.ops.run_index import build_index_entry, refresh_run_index


def test_refresh_run_index(tmp_path, monkeypatch):
    root = tmp_path / ".pipeline" / "runs"
    bundle = root / "run_1" / "artifacts.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text(
        '{"run_id": "run_1", "stage": "generate", "npc_key": "history_guide", "technique": "ollama", "created_at": "now", "metrics": {"pass_rate": 1.0}, "artifacts": {"train": "x"}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.core.ops.run_index.CANONICAL_RUNS_ROOT", root)
    index_path = tmp_path / "runs_index.jsonl"
    entries = refresh_run_index(root=root, index_path=index_path)
    assert len(entries) == 1
    assert index_path.exists()
    assert '"run_id": "run_1"' in index_path.read_text(encoding="utf-8")


def test_build_index_entry_uses_bundle_fields(tmp_path):
    bundle_path = tmp_path / "artifacts.json"
    bundle = {
        "run_id": "run_2",
        "stage": "dataset_eval",
        "npc_key": "chef_assistant",
        "technique": "ollama",
        "created_at": "now",
        "metrics": {"pass_rate": 0.5},
    }
    entry = build_index_entry(bundle, bundle_path)
    assert entry.run_id == "run_2"
    assert entry.stage == "dataset_eval"
    assert entry.npc_key == "chef_assistant"
