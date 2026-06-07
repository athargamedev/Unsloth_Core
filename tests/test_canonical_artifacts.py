from src.core.ops.canonical_artifacts import (
    CanonicalArtifactBundle,
    canonical_bundle_path,
    record_canonical_bundle,
    write_canonical_bundle,
)


def test_write_canonical_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.core.ops.canonical_artifacts.CANONICAL_RUNS_ROOT", tmp_path / ".pipeline" / "runs"
    )
    bundle = CanonicalArtifactBundle(
        run_id="run_1",
        stage="generate",
        npc_key="history_guide",
        technique="ollama",
        created_at="2026-01-01T00:00:00+00:00",
        artifacts={"train": "/tmp/train.jsonl"},
        metrics={"rows": 10},
        metadata={"note": "ok"},
    )
    path = write_canonical_bundle(bundle)
    assert path == canonical_bundle_path("run_1")
    assert path.exists()
    payload = path.read_text(encoding="utf-8")
    assert '"stage": "generate"' in payload
    assert '"history_guide"' in payload


def test_record_canonical_bundle_forwards_lineage_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.core.ops.canonical_artifacts.CANONICAL_RUNS_ROOT", tmp_path / ".pipeline" / "runs"
    )
    captured = {}

    def fake_record(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(
        "src.core.ops.canonical_artifacts.record_stage_artifacts_best_effort",
        fake_record,
    )
    input_records = [{"artifact_type": "dataset_clean", "sha256": "abc"}]

    record_canonical_bundle(
        run_id="run_2",
        stage="dataset_eval",
        npc_key="history_guide",
        technique="ollama",
        artifacts={"quality_summary": str(tmp_path / "quality_summary.json")},
        input_records=input_records,
    )

    assert captured["kwargs"]["input_records"] == input_records
