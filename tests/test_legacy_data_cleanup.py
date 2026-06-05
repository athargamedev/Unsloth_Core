def test_legacy_cleanup_identifies_subjects_mirror_and_stale_snapshots(monkeypatch, tmp_path):
    from src.core.ops import legacy_data_cleanup as ldc

    monkeypatch.setattr(ldc, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ldc, "dataset_root", lambda: tmp_path / "data" / "datasets")

    subjects = tmp_path / "subjects" / "datasets" / "npc" / "ollama"
    subjects.mkdir(parents=True)
    legacy_file = subjects / "quality_summary.json"
    legacy_file.write_text("{}")

    data_hist = tmp_path / "data" / "datasets" / "npc" / "ollama" / "history"
    data_hist.mkdir(parents=True)
    stale = data_hist / "quality_summary_fast.json"
    stale.write_text("{}")

    names = {(t.path.name, t.reason) for t in ldc.iter_legacy_dataset_artifacts(tmp_path)}

    assert ("quality_summary.json", "legacy subjects/datasets mirror") in names
    assert ("quality_summary_fast.json", "stale backup/snapshot artifact") in names
