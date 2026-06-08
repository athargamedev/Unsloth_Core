"""Tests for PipelineBundle — report bundle builder."""

from __future__ import annotations

import json
from pathlib import Path


def _make_quality_summary(tmp_path: Path) -> Path:
    p = tmp_path / "data" / "datasets" / "chef_assistant" / "ollama" / "quality_summary.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "status": "ok",
                "pass_rate": 0.6,
                "total": 5,
                "passed": 3,
                "failed": 2,
                "failures": [],
                "results": [
                    {"category": "identity", "score": 0.8, "reasoning": "good"},
                    {"category": "teaching", "score": 0.5, "reasoning": "needs work"},
                ],
                "is_pass": True,
                "diagnostic_pass_rate": 1.0,
            }
        )
    )
    return p


def _make_feedback_json(tmp_path: Path) -> Path:
    p = tmp_path / "artifacts" / "eval" / "results" / "feedback" / "chef_assistant.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(
            {
                "overall_win_rate": 0.55,
                "total_games": 9,
                "candidate_wins": 5,
                "baseline_wins": 4,
                "weak_concepts": ["identity", "refusal"],
                "avg_candidate_words": 35,
                "avg_baseline_words": 42,
            }
        )
    )
    return p


def _make_artifact_registry(tmp_path: Path) -> Path:
    p = tmp_path / "artifacts.jsonl"
    entries = [
        {
            "ts": "2026-06-07T00:00:00",
            "run_id": "run_001",
            "npc_key": "chef_assistant",
            "stage": "generate",
            "artifact_type": "dataset_raw",
            "path": str(
                tmp_path / "data" / "datasets" / "chef_assistant" / "ollama" / "train.jsonl"
            ),
            "technique": "ollama",
            "size_bytes": 1000,
            "sha256": "abc123",
        },
        {
            "ts": "2026-06-07T00:01:00",
            "run_id": "run_002",
            "npc_key": "chef_assistant",
            "stage": "sanitize",
            "artifact_type": "dataset_clean",
            "path": str(
                tmp_path / "data" / "datasets" / "chef_assistant" / "ollama" / "train_clean.jsonl"
            ),
            "technique": "ollama",
            "size_bytes": 2000,
            "sha256": "def456",
        },
    ]
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return p


def _make_run_registry(tmp_path: Path) -> Path:
    p = tmp_path / "runs.jsonl"
    entries = [
        {
            "run_id": "train_001",
            "npc_key": "chef_assistant",
            "stage": "train",
            "loss": 3.91,
            "train_samples": 72,
            "export_gguf": True,
            "status": "completed",
        }
    ]
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return p


def _make_spec(tmp_path: Path, npc_key: str = "chef_assistant") -> Path:
    p = tmp_path / "data" / "npcs" / "specs" / f"{npc_key}.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps({"npc_key": npc_key, "name": "Chef Assistant", "description": "Culinary NPC"})
    )
    return p


def test_bundle_collects_fragments(tmp_path):
    """Bundle builder collects fragments from existing artifacts without errors."""
    from src.core.reports.pipeline_bundle import build_pipeline_bundle

    # Setup test data
    _make_quality_summary(tmp_path)
    _make_feedback_json(tmp_path)
    artifact_index = _make_artifact_registry(tmp_path)
    run_index = _make_run_registry(tmp_path)
    _make_spec(tmp_path)

    report_dir = tmp_path / "report_bundle"

    result = build_pipeline_bundle(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
        report_dir=report_dir,
        data_root=tmp_path,
        artifact_index=artifact_index,
        run_index=run_index,
    )

    assert result["npc_key"] == "chef_assistant"
    assert result["profile"] == "npc-production-grounded"
    assert result["ok"] is not None
    assert "run_spec" in result
    assert "integration_audit" in result
    assert "stage_fragments" in result
    assert "summary" in result

    # Verify files written
    assert (report_dir / "pipeline_run_spec.json").exists()
    assert (report_dir / "stage_status.json").exists()
    assert (report_dir / "integration_health.json").exists()
    assert (report_dir / "summary.md").exists()
    assert (report_dir / "index.html").exists()
    assert (report_dir / "next_actions.json").exists()

    # Verify content
    summary = (report_dir / "summary.md").read_text()
    assert "chef_assistant" in summary
    assert "3/5" in summary  # pass count

    index = (report_dir / "index.html").read_text()
    assert "Pipeline Report" in index
    assert "chef_assistant" in index

    next_actions = json.loads((report_dir / "next_actions.json").read_text())
    assert isinstance(next_actions, list)


def test_bundle_tolerates_missing_data(tmp_path):
    """Bundle builder works with minimal data — no quality, no feedback."""
    from src.core.reports.pipeline_bundle import build_pipeline_bundle

    _make_spec(tmp_path)
    report_dir = tmp_path / "sparse_bundle"

    result = build_pipeline_bundle(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
        report_dir=report_dir,
        data_root=tmp_path,
    )

    assert result["npc_key"] == "chef_assistant"
    assert (report_dir / "summary.md").exists()
    assert (report_dir / "index.html").exists()
    assert (report_dir / "pipeline_run_spec.json").exists()


def test_bundle_export_accessibility(tmp_path):
    """Bundle builder exports named report files that are parseable JSON."""
    from src.core.reports.pipeline_bundle import build_pipeline_bundle

    _make_quality_summary(tmp_path)
    _make_feedback_json(tmp_path)
    _make_spec(tmp_path)
    report_dir = tmp_path / "accessible_bundle"

    build_pipeline_bundle(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
        report_dir=report_dir,
        data_root=tmp_path,
    )

    # All JSON fragments should be parseable
    json_files = list(report_dir.glob("*.json"))
    assert len(json_files) >= 4
    for jf in json_files:
        data = json.loads(jf.read_text())
        assert data is not None


def test_bundle_blocks_parameter_comparison_when_runtime_eval_loses(tmp_path):
    """A measured runtime loss should route to repair, not parameter comparison."""
    from src.core.reports.pipeline_bundle import build_pipeline_bundle

    _make_quality_summary(tmp_path)
    _make_run_registry(tmp_path)
    _make_spec(tmp_path)
    feedback = tmp_path / "artifacts" / "eval" / "results" / "feedback" / "chef_assistant.json"
    feedback.parent.mkdir(parents=True, exist_ok=True)
    feedback.write_text(
        json.dumps(
            {
                "win_rate": 0.3,
                "total_examples": 10,
                "candidate_wins": 3,
                "baseline_wins": 6,
                "ties": 1,
                "weak_concepts": ["teaching/kitchen workflow"],
                "avg_candidate_words": 25.9,
                "avg_baseline_words": 94.0,
            }
        )
    )
    report_dir = tmp_path / "losing_bundle"

    build_pipeline_bundle(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
        report_dir=report_dir,
        data_root=tmp_path,
    )

    summary = (report_dir / "summary.md").read_text()
    assert "Not yet" in summary
    assert "Runtime eval below" in summary

    next_actions = json.loads((report_dir / "next_actions.json").read_text())
    action_names = [a["action"] for a in next_actions]
    assert "Repair runtime answer density and specificity" in action_names
    assert "Run parameter comparison experiments" not in action_names


def test_bundle_uses_custom_run_index_for_training_report(tmp_path):
    """Custom run_index should populate training_report.json."""
    from src.core.reports.pipeline_bundle import build_pipeline_bundle

    _make_quality_summary(tmp_path)
    _make_feedback_json(tmp_path)
    _make_spec(tmp_path)
    run_index = _make_run_registry(tmp_path)
    report_dir = tmp_path / "custom_run_index_bundle"

    build_pipeline_bundle(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
        report_dir=report_dir,
        data_root=tmp_path,
        run_index=run_index,
    )

    training = json.loads((report_dir / "training_report.json").read_text())
    assert training["available"] is True
    assert training["runs"][0]["run_id"] == "train_001"
    assert training["runs"][0]["source"] == run_index.name


def test_bundle_escapes_dynamic_html(tmp_path):
    """HTML reports must escape data from CLI args and artifact JSON."""
    from src.core.reports.pipeline_bundle import build_pipeline_bundle

    npc_key = "chef_assistant"
    _make_quality_summary(tmp_path)
    feedback = tmp_path / "artifacts" / "eval" / "results" / "feedback" / f"{npc_key}.json"
    feedback.parent.mkdir(parents=True, exist_ok=True)
    feedback.write_text(
        json.dumps({"win_rate": 0.0, "total_examples": 1, "weak_concepts": ["<b>bad</b>"]})
    )
    _make_spec(tmp_path, npc_key=npc_key)
    report_dir = tmp_path / "escaped_bundle"

    build_pipeline_bundle(
        npc_key=npc_key,
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
        report_dir=report_dir,
        data_root=tmp_path,
    )

    html = (report_dir / "index.html").read_text()
    assert "<b>bad</b>" not in html
    assert "&lt;b&gt;bad&lt;/b&gt;" in html
