from pathlib import Path

from src.core.ops.canonical_artifacts import CanonicalArtifactBundle, canonical_bundle_path, write_canonical_bundle


def test_write_canonical_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.ops.canonical_artifacts.CANONICAL_RUNS_ROOT", tmp_path / ".pipeline" / "runs")
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
