from __future__ import annotations


def _ctx(npc_key: str = "history_guide"):
    from src.core.orchestration.workflow_spec import WorkflowContext

    return WorkflowContext(npc_key=npc_key)


def _cmd(stage: str, npc_key: str = "history_guide") -> list[str]:
    from src.core.orchestration.workflow_spec import build_stage_command

    return build_stage_command(_ctx(npc_key), stage)


def test_ollama_generate_uses_production_command_and_current_default():
    cmd = _cmd("generate")

    assert cmd[:2] == ["./ucore", "generate-ollama"]
    assert "data/npcs/specs/history_guide.json" in cmd
    assert "--model" in cmd
    assert "qwen2.5:7b" in cmd
    assert "generate_dataset.py" not in " ".join(cmd)


def test_sanitize_command_has_input_output_and_strict_flags():
    cmd = _cmd("sanitize")

    assert cmd[:2] == ["./ucore", "sanitize"]
    assert "data/datasets/history_guide/ollama/train.jsonl" in cmd
    assert "--output" in cmd
    assert "data/datasets/history_guide/ollama/train_clean.jsonl" in cmd
    assert "--strict-canonical" in cmd
    assert "--require-complete-metadata" in cmd


def test_dataset_eval_uses_spec_technique_mode_and_current_judge_default():
    cmd = _cmd("dataset_eval")

    assert cmd[:2] == ["./ucore", "dataset-eval"]
    assert "data/npcs/specs/history_guide.json" in cmd
    assert "--technique" in cmd
    assert "ollama" in cmd
    assert "--mode" in cmd
    assert "fast" in cmd
    assert "--judge-model" in cmd
    assert "qwen2.5:7b" in cmd
    assert "--output" in cmd
    assert "data/datasets/history_guide/ollama/quality_summary.json" in cmd


def test_train_exports_gguf_and_never_allows_ungated_dataset_by_default():
    cmd = _cmd("train")

    assert cmd[:2] == ["./ucore", "train"]
    assert "data/npcs/specs/history_guide.json" in cmd
    assert "--technique" in cmd
    assert "ollama" in cmd
    assert "--preset" in cmd
    assert "fast-3b" in cmd
    assert "--export-gguf" in cmd
    assert "--allow-ungated-dataset" not in cmd


def test_export_command_targets_npc_key():
    cmd = _cmd("export")

    assert cmd[:2] == ["./ucore", "export"]
    assert "history_guide" in cmd


def test_evaluate_command_uses_adapter_feedback_and_report_html():
    cmd = _cmd("evaluate")

    assert cmd[:2] == ["./ucore", "evaluate"]
    assert "--candidate" in cmd
    assert "artifacts/exports/history_guide/history_guide-lora-f16.gguf" in cmd
    assert "--spec" in cmd
    assert "data/npcs/specs/history_guide.json" in cmd
    assert "--feedback-json" in cmd
    assert "artifacts/eval/results/feedback/history_guide.json" in cmd
    assert "--report-html" in cmd


def test_all_stage_commands_avoid_deprecated_paths():
    from src.core.orchestration.workflow_spec import CANONICAL_WORKFLOW_STAGES, build_stage_command

    for stage in CANONICAL_WORKFLOW_STAGES:
        cmd = build_stage_command(_ctx(), stage)
        rendered = " ".join(cmd)
        assert "subjects/" not in rendered
        assert not any(part.startswith("outputs/") for part in cmd)
        assert not any(part.startswith("exports/") for part in cmd)
        assert not any(part.startswith("eval/") for part in cmd)


def test_unknown_stage_is_rejected():
    import pytest

    from src.core.orchestration.workflow_spec import build_stage_command

    with pytest.raises(ValueError, match="Unknown workflow stage"):
        build_stage_command(_ctx(), "not_a_stage")
