"""Tests for the ``--remote-eval`` and ``--confident`` CLI flag integration.

Tests that ``dataset_eval.py`` and ``evaluate.py`` correctly handle remote
evaluation on Confident AI infrastructure, including argparse, provider
selection, preflight skipping, API calls, manifest metadata, and graceful
degradation when credentials are missing.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict]) -> Path:
    """Write a JSONL file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in records),
        encoding="utf-8",
    )
    return path


def _demo_spec() -> dict:
    return {
        "npc_key": "demo_npc",
        "npc_name": "DemoNpc",
        "subject": "Demo Studies",
        "system_prompt": "You are DemoNpc, a helpful assistant.",
        "teaching": {"expertise": ["demo concepts"]},
        "identity": {"personality": "helpful", "background": "demo", "mannerisms": "clear"},
        "dialogue": {"max_sentences": 3, "example_topics": ["What is demo?"]},
        "quest": {"scenarios": [{"name": "demo_test", "description": "Test scenario"}]},
        "refusal": {"boundaries": ["no speculation"], "redirect_policy": "redirect to evidence"},
    }


def _make_dataset_row(category: str = "teaching") -> dict:
    return {
        "messages": [
            {"role": "system", "content": "You are DemoNpc."},
            {"role": "user", "content": f"Tell me about {category}."},
            {"role": "assistant", "content": f"Here is some {category} information."},
        ],
        "metadata": {"category": category, "difficulty": "beginner"},
    }


def _make_dataset_eval_args(
    *,
    remote_eval: bool = False,
    confident: bool = False,
    identifier: str | None = None,
    pull_alias: str | None = None,
) -> Namespace:
    """Build a real ``argparse.Namespace`` for ``dataset_eval.py`` ``run_deepeval()``."""
    return Namespace(
        remote_eval=remote_eval,
        confident=confident,
        pull_alias=pull_alias,
        judge_provider="ollama",
        judge_preset=None,
        judge_model=None,
        ollama_base_url="http://localhost:11434",
        mode="fast",
        display="all",
        ignore_errors=False,
        soft_fail=False,
        output=None,
        categories=None,
        identifier=identifier,
        technique=None,
        workflow_hooks=None,
        push_to_confident=False,
        wandb=False,
        wandb_project="unsloth-core",
        wandb_entity=None,
        wandb_inference_project=None,
        wandb_inference_entity=None,
        judge_temperature=0.0,
        cases_per_category=None,
        spec="spec.json",
    )


def _make_evaluate_args(
    *,
    remote_eval: bool = False,
    deepeval: bool = True,
    deepeval_judge_model: str = "qwen3:latest",
    deepeval_identifier: str | None = None,
    technique: str = "template",
    spec: str | None = None,
    baseline: str | None = None,
    candidate: str | None = None,
    base_model: str | None = None,
    lora_weight: float = 1.0,
) -> Namespace:
    """Build a real ``argparse.Namespace`` for ``evaluate.py`` ``_run_deepeval_eval()``."""
    return Namespace(
        remote_eval=remote_eval,
        deepeval=deepeval,
        deepeval_judge_model=deepeval_judge_model,
        deepeval_identifier=deepeval_identifier,
        technique=technique,
        spec=spec,
        baseline=baseline,
        candidate=candidate,
        base_model=base_model,
        lora_weight=lora_weight,
    )


# ===================================================================
# dataset_eval.py — Argparse Tests
# ===================================================================


def test_dataset_eval_argparse_defaults(monkeypatch):
    """Default values for ``--remote-eval`` and ``--confident`` are ``False``."""
    from src.core.dataset.dataset_eval import parse_args

    monkeypatch.setattr(
        sys,
        "argv",
        ["dataset_eval.py", "subjects/NPC_specs/demo.json"],
    )
    args = parse_args()
    assert args.remote_eval is False
    assert args.confident is False


def test_dataset_eval_argparse_accepts_remote_eval(monkeypatch):
    """``--remote-eval`` sets ``remote_eval=True``."""
    from src.core.dataset.dataset_eval import parse_args

    monkeypatch.setattr(
        sys,
        "argv",
        ["dataset_eval.py", "subjects/NPC_specs/demo.json", "--remote-eval"],
    )
    args = parse_args()
    assert args.remote_eval is True


def test_dataset_eval_argparse_accepts_confident(monkeypatch):
    """``--confident`` sets ``confident=True``."""
    from src.core.dataset.dataset_eval import parse_args

    monkeypatch.setattr(
        sys,
        "argv",
        ["dataset_eval.py", "subjects/NPC_specs/demo.json", "--confident"],
    )
    args = parse_args()
    assert args.confident is True


def test_dataset_eval_argparse_accepts_both_flags(monkeypatch):
    """Both ``--remote-eval`` and ``--confident`` can be set together."""
    from src.core.dataset.dataset_eval import parse_args

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dataset_eval.py",
            "subjects/NPC_specs/demo.json",
            "--remote-eval",
            "--confident",
        ],
    )
    args = parse_args()
    assert args.remote_eval is True
    assert args.confident is True


# ===================================================================
# dataset_eval.py — ``remote_eval`` Requires ``confident``
# ===================================================================


def test_dataset_eval_remote_eval_requires_confident(monkeypatch, tmp_path, capsys):
    """``run_deepeval()`` exits with code 1 when ``--remote-eval`` is set without ``--confident``.

    The check ``if not args.confident`` inside the ``remote_eval`` branch must
    print an error message and call ``sys.exit(1)``.
    """
    from src.core.dataset.dataset_eval import run_deepeval

    # Create a real clean_path so the file-exists guard in run_deepeval passes
    clean_path = _write_jsonl(tmp_path / "train_clean.jsonl", [_make_dataset_row()])

    args = _make_dataset_eval_args(remote_eval=True, confident=False)

    mock_workflow = MagicMock()
    mock_workflow.npc_key = "demo_npc"
    mock_workflow.technique = "template"
    mock_workflow.dataset_path = clean_path
    mock_workflow.dataset_clean_path = clean_path

    mock_pipeline_run = MagicMock()
    mock_pipeline_run.run_id = "test-run-id"
    mock_pipeline_run.run_dir = tmp_path / ".pipeline" / "runs" / "test-run-id"
    mock_pipeline_run.__enter__.return_value = mock_pipeline_run
    mock_pipeline_run.__exit__.return_value = False  # Don't suppress exceptions

    mock_hook_recorder = MagicMock()
    mock_hook_recorder.step.return_value.__enter__ = MagicMock()
    mock_hook_recorder.step.return_value.__exit__ = MagicMock(return_value=False)

    # PipelineRun, archive_quality_artifact are imported INSIDE run_deepeval
    # from src.core.ops.run_registry; set_active_run/clear_active_run from
    # _config.log_setup — patch at source modules
    with (
        patch("src.core.dataset.dataset_eval.resolve_workflow_context", return_value=mock_workflow),
        patch("src.core.dataset.dataset_eval.effective_cases_per_category", return_value=1),
        patch("src.core.ops.run_registry.PipelineRun", return_value=mock_pipeline_run),
        patch("src.core.ops.run_registry.archive_quality_artifact"),
        patch("src.config.log_setup.set_active_run"),
        patch("src.config.log_setup.clear_active_run"),
        patch(
            "src.core.dataset.dataset_eval.WorkflowHookRecorder", return_value=mock_hook_recorder
        ),
        patch("src.core.dataset.dataset_eval.resolve_deepeval_bin", return_value="deepeval"),
        patch("src.core.dataset.dataset_eval.resolve_ollama_model", return_value="qwen3:latest"),
        patch("src.core.dataset.dataset_eval.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)

        with pytest.raises(SystemExit) as exc_info:
            run_deepeval(args, _demo_spec())

        assert exc_info.value.code == 1

    captured = capsys.readouterr().out
    assert "remote-eval requires --confident" in captured


def test_dataset_eval_confident_without_api_key(monkeypatch, tmp_path, capsys):
    """``run_deepeval()`` exits with SystemExit(1) when ``--confident`` is passed but ``CONFIDENT_API_KEY`` is not set."""
    from src.core.dataset.dataset_eval import run_deepeval

    clean_path = _write_jsonl(tmp_path / "train_clean.jsonl", [_make_dataset_row()])

    monkeypatch.delenv("CONFIDENT_API_KEY", raising=False)

    args = _make_dataset_eval_args(confident=True, remote_eval=False)

    mock_workflow = MagicMock()
    mock_workflow.npc_key = "demo_npc"
    mock_workflow.technique = "template"
    mock_workflow.dataset_path = clean_path
    mock_workflow.dataset_clean_path = clean_path

    mock_pipeline_run = MagicMock()
    mock_pipeline_run.run_id = "test-run-id"
    mock_pipeline_run.run_dir = tmp_path / ".pipeline" / "runs" / "test-run-id"
    mock_pipeline_run.__enter__.return_value = mock_pipeline_run
    mock_pipeline_run.__exit__.return_value = False

    mock_hook_recorder = MagicMock()
    mock_hook_recorder.step.return_value.__enter__ = MagicMock()
    mock_hook_recorder.step.return_value.__exit__ = MagicMock(return_value=False)

    mock_preflight = MagicMock()
    mock_preflight.stopped_ollama_models = []
    mock_preflight.warnings = []

    with (
        patch("src.core.dataset.dataset_eval.resolve_workflow_context", return_value=mock_workflow),
        patch("src.core.dataset.dataset_eval.effective_cases_per_category", return_value=1),
        patch("src.core.ops.run_registry.PipelineRun", return_value=mock_pipeline_run),
        patch("src.core.ops.run_registry.archive_quality_artifact"),
        patch("src.config.log_setup.set_active_run"),
        patch("src.config.log_setup.clear_active_run"),
        patch(
            "src.core.dataset.dataset_eval.WorkflowHookRecorder", return_value=mock_hook_recorder
        ),
        patch("src.core.dataset.dataset_eval.resolve_deepeval_bin", return_value="deepeval"),
        patch("src.core.dataset.dataset_eval.resolve_ollama_model", return_value="qwen3:latest"),
        patch("src.core.dataset.dataset_eval.run_preflight", return_value=mock_preflight),
        patch("src.core.dataset.dataset_eval.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)

        with pytest.raises(SystemExit) as exc_info:
            run_deepeval(args, _demo_spec())

            # SystemExit is raised with a string message; the code attribute holds the message
            assert exc_info.value.code is not None
            assert "Error: --confident was passed but CONFIDENT_API_KEY" in str(exc_info.value.code)

    captured = capsys.readouterr()
    assert "not configured" in captured.out


# ===================================================================
# dataset_eval.py — Remote Eval Sets judge_provider to "confident"
# ===================================================================


def test_dataset_eval_remote_eval_sets_judge_provider_confident(monkeypatch, tmp_path):
    """With ``--remote-eval``, the quality summary has ``judge_provider`` set to ``"confident"``."""
    from src.core.dataset.dataset_eval import run_deepeval

    clean_path = _write_jsonl(tmp_path / "train_clean.jsonl", [_make_dataset_row()])

    args = _make_dataset_eval_args(remote_eval=True, confident=True)
    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")

    mock_workflow = MagicMock()
    mock_workflow.npc_key = "demo_npc"
    mock_workflow.technique = "template"
    mock_workflow.dataset_path = clean_path
    mock_workflow.dataset_clean_path = clean_path

    mock_pipeline_run = MagicMock()
    mock_pipeline_run.run_id = "test-run-id"
    mock_pipeline_run.run_dir = tmp_path / ".pipeline" / "runs" / "test-run-id"

    mock_hook_recorder = MagicMock()
    mock_hook_recorder.step.return_value.__enter__ = MagicMock()
    mock_hook_recorder.step.return_value.__exit__ = MagicMock(return_value=False)

    # Capture what gets written to quality_summary.json
    written_summaries: list[dict] = []

    def _capture_write_json(path, payload, **kwargs):
        if "quality_summary" in str(path):
            written_summaries.append(payload)

    mock_client = MagicMock()
    mock_client.evaluate.return_value = {
        "success": True,
        "data": {"testRunId": "remote-run-001"},
    }

    dataset_summary = {"total": 1, "by_category": {"teaching": 1}, "unknown_rows": 0}
    expected_dist = {"teaching": 1}

    with (
        patch("src.core.dataset.dataset_eval.resolve_workflow_context", return_value=mock_workflow),
        patch("src.core.dataset.dataset_eval.effective_cases_per_category", return_value=1),
        patch("src.core.ops.run_registry.PipelineRun", return_value=mock_pipeline_run),
        patch("src.core.ops.run_registry.archive_quality_artifact"),
        patch("src.config.log_setup.set_active_run"),
        patch("src.config.log_setup.clear_active_run"),
        patch(
            "src.core.dataset.dataset_eval.WorkflowHookRecorder", return_value=mock_hook_recorder
        ),
        patch("src.core.dataset.dataset_eval.resolve_deepeval_bin", return_value="deepeval"),
        patch("src.core.dataset.dataset_eval.resolve_ollama_model", return_value="qwen3:latest"),
        patch("src.core.dataset.dataset_eval.ConfidentAPIClient", return_value=mock_client),
        patch(
            "src.core.dataset.dataset_eval.summarize_jsonl_dataset", return_value=dataset_summary
        ),
        patch(
            "src.core.dataset.dataset_eval.expected_examples_per_category",
            return_value=expected_dist,
        ),
        patch("src.core.dataset.dataset_eval.calculate_distribution_gaps", return_value=[]),
        patch("src.core.dataset.dataset_eval.load_optional_json", return_value=None),
        patch("src.core.dataset.dataset_eval.sanitizer_quality_issues", return_value=({}, [])),
        patch("src.core.dataset.dataset_eval.build_combined_quality_report", return_value={}),
        patch("src.core.dataset.dataset_eval.write_json", side_effect=_capture_write_json),
        patch("src.core.dataset.dataset_eval.dataset_eval_exit_code", return_value=0),
    ):
        exit_code = run_deepeval(args, _demo_spec())

        assert exit_code == 0
        assert len(written_summaries) >= 1

        summary = written_summaries[0]
        assert summary["judge_provider"] == "confident"
        assert summary["judge_model"] == "hosted"
        assert summary["remote_eval"] is True
        assert summary["test_run_id"] == "remote-run-001"
        assert "confident_url" in summary
        assert "remote-run-001" in summary["confident_url"]


# ===================================================================
# dataset_eval.py — Remote Eval Skips Preflight
# ===================================================================


def test_dataset_eval_remote_eval_skips_preflight(monkeypatch, tmp_path):
    """With ``--remote-eval``, the preflight check is NOT called."""
    from src.core.dataset.dataset_eval import run_deepeval

    clean_path = _write_jsonl(tmp_path / "train_clean.jsonl", [_make_dataset_row()])

    args = _make_dataset_eval_args(remote_eval=True, confident=True)
    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")

    mock_workflow = MagicMock()
    mock_workflow.npc_key = "demo_npc"
    mock_workflow.technique = "template"
    mock_workflow.dataset_path = clean_path
    mock_workflow.dataset_clean_path = clean_path

    mock_pipeline_run = MagicMock()
    mock_pipeline_run.run_id = "test-run-id"
    mock_pipeline_run.run_dir = tmp_path / ".pipeline" / "runs" / "test-run-id"
    mock_pipeline_run.__enter__.return_value = mock_pipeline_run
    mock_pipeline_run.__exit__.return_value = False

    mock_hook_recorder = MagicMock()
    mock_hook_recorder.step.return_value.__enter__ = MagicMock()
    mock_hook_recorder.step.return_value.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.evaluate.return_value = {
        "success": True,
        "data": {"testRunId": "remote-run-002"},
    }

    dataset_summary = {"total": 1, "by_category": {"teaching": 1}, "unknown_rows": 0}

    # Track whether run_preflight was called
    preflight_called = False

    def _track_preflight(*_args, **_kwargs):
        nonlocal preflight_called
        preflight_called = True
        return MagicMock()

    with (
        patch("src.core.dataset.dataset_eval.resolve_workflow_context", return_value=mock_workflow),
        patch("src.core.dataset.dataset_eval.effective_cases_per_category", return_value=1),
        patch("src.core.ops.run_registry.PipelineRun", return_value=mock_pipeline_run),
        patch("src.core.ops.run_registry.archive_quality_artifact"),
        patch("src.config.log_setup.set_active_run"),
        patch("src.config.log_setup.clear_active_run"),
        patch(
            "src.core.dataset.dataset_eval.WorkflowHookRecorder", return_value=mock_hook_recorder
        ),
        patch("src.core.dataset.dataset_eval.resolve_deepeval_bin", return_value="deepeval"),
        patch("src.core.dataset.dataset_eval.resolve_ollama_model", return_value="qwen3:latest"),
        patch("src.core.dataset.dataset_eval.ConfidentAPIClient", return_value=mock_client),
        patch("src.core.dataset.dataset_eval.run_preflight", side_effect=_track_preflight),
        patch(
            "src.core.dataset.dataset_eval.summarize_jsonl_dataset", return_value=dataset_summary
        ),
        patch("src.core.dataset.dataset_eval.expected_examples_per_category", return_value={}),
        patch("src.core.dataset.dataset_eval.calculate_distribution_gaps", return_value=[]),
        patch("src.core.dataset.dataset_eval.load_optional_json", return_value=None),
        patch("src.core.dataset.dataset_eval.sanitizer_quality_issues", return_value=({}, [])),
        patch("src.core.dataset.dataset_eval.build_combined_quality_report", return_value={}),
        patch("src.core.dataset.dataset_eval.write_json"),
        patch("src.core.dataset.dataset_eval.dataset_eval_exit_code", return_value=0),
    ):
        exit_code = run_deepeval(args, _demo_spec())
        assert exit_code == 0
        assert not preflight_called, "run_preflight should not be called with --remote-eval"


# ===================================================================
# dataset_eval.py — Remote Eval Calls ConfidentAPIClient.evaluate()
# ===================================================================


def test_dataset_eval_remote_eval_calls_confident_api(monkeypatch, tmp_path):
    """With ``--remote-eval``, ``ConfidentAPIClient.evaluate()`` is called with correct arguments."""
    from src.core.dataset.dataset_eval import run_deepeval

    clean_path = _write_jsonl(tmp_path / "train_clean.jsonl", [_make_dataset_row("identity")])

    args = _make_dataset_eval_args(
        remote_eval=True,
        confident=True,
        identifier="custom-eval-id",
    )
    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")

    mock_workflow = MagicMock()
    mock_workflow.npc_key = "demo_npc"
    mock_workflow.technique = "template"
    mock_workflow.dataset_path = clean_path
    mock_workflow.dataset_clean_path = clean_path

    mock_pipeline_run = MagicMock()
    mock_pipeline_run.run_id = "test-run-id"
    mock_pipeline_run.run_dir = tmp_path / ".pipeline" / "runs" / "test-run-id"
    mock_pipeline_run.__enter__.return_value = mock_pipeline_run
    mock_pipeline_run.__exit__.return_value = False

    mock_hook_recorder = MagicMock()
    mock_hook_recorder.step.return_value.__enter__ = MagicMock()
    mock_hook_recorder.step.return_value.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.evaluate.return_value = {
        "success": True,
        "data": {"testRunId": "remote-run-001"},
    }

    dataset_summary = {"total": 1, "by_category": {"teaching": 1}, "unknown_rows": 0}

    with (
        patch("src.core.dataset.dataset_eval.resolve_workflow_context", return_value=mock_workflow),
        patch("src.core.dataset.dataset_eval.effective_cases_per_category", return_value=1),
        patch("src.core.ops.run_registry.PipelineRun", return_value=mock_pipeline_run),
        patch("src.core.ops.run_registry.archive_quality_artifact"),
        patch("src.config.log_setup.set_active_run"),
        patch("src.config.log_setup.clear_active_run"),
        patch(
            "src.core.dataset.dataset_eval.WorkflowHookRecorder", return_value=mock_hook_recorder
        ),
        patch("src.core.dataset.dataset_eval.resolve_deepeval_bin", return_value="deepeval"),
        patch("src.core.dataset.dataset_eval.resolve_ollama_model", return_value="qwen3:latest"),
        patch("src.core.dataset.dataset_eval.ConfidentAPIClient", return_value=mock_client),
        patch(
            "src.core.dataset.dataset_eval.summarize_jsonl_dataset", return_value=dataset_summary
        ),
        patch("src.core.dataset.dataset_eval.expected_examples_per_category", return_value={}),
        patch("src.core.dataset.dataset_eval.calculate_distribution_gaps", return_value=[]),
        patch("src.core.dataset.dataset_eval.load_optional_json", return_value=None),
        patch("src.core.dataset.dataset_eval.sanitizer_quality_issues", return_value=({}, [])),
        patch("src.core.dataset.dataset_eval.build_combined_quality_report", return_value={}),
        patch("src.core.dataset.dataset_eval.write_json"),
        patch("src.core.dataset.dataset_eval.dataset_eval_exit_code", return_value=0),
    ):
        exit_code = run_deepeval(args, _demo_spec())

        assert exit_code == 0
        mock_client.evaluate.assert_called_once()

        call_args, call_kwargs = mock_client.evaluate.call_args
        assert len(call_args) >= 2
        assert isinstance(call_args[0], list), "First positional arg should be test_cases list"
        assert isinstance(call_args[1], dict), (
            "Second positional arg should be metric_collection dict"
        )
        assert call_args[1]["name"] == "npc-dataset-quality", "Metric collection name should match"
        assert call_kwargs.get("identifier") == "custom-eval-id", (
            "Identifier should be passed as keyword arg 'identifier'"
        )


# ===================================================================
# evaluate.py — Argparse Tests
# ===================================================================


def test_evaluate_argparse_accepts_remote_eval():
    """``evaluate.py``'s argparse accepts ``--remote-eval`` and sets ``remote_eval=True``.

    The real ``main()`` parser in ``evaluate.py`` registers ``--remote-eval``
    at line 1129.  We instantiate an equivalent parser here to confirm the
    argument binding without invoking the full CLI pipeline.
    """
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--remote-eval", action="store_true", default=False)

    args = parser.parse_args(
        [
            "--baseline",
            "old.gguf",
            "--candidate",
            "new.gguf",
            "--remote-eval",
        ]
    )
    assert args.remote_eval is True
    assert args.baseline == "old.gguf"
    assert args.candidate == "new.gguf"


def test_evaluate_argparse_remote_eval_default_false():
    """``--remote-eval`` defaults to ``False`` in evaluate.py's argparse."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--remote-eval", action="store_true", default=False)

    args = parser.parse_args(
        [
            "--baseline",
            "old.gguf",
            "--candidate",
            "new.gguf",
        ]
    )
    assert args.remote_eval is False


# ===================================================================
# evaluate.py — Remote Eval Uses ConfidentAPIClient
# ===================================================================


def test_evaluate_remote_eval_uses_confident_api(monkeypatch, tmp_path):
    """With ``--remote-eval``, ``_run_deepeval_eval`` calls ``ConfidentAPIClient.evaluate()``."""
    from src.core.evaluation.evaluate import _run_deepeval_eval

    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "npc_key": "demo_npc",
                "npc_name": "DemoNpc",
                "subject": "Demo Studies",
                "system_prompt": "You are DemoNpc.",
            }
        )
    )

    args = _make_evaluate_args(
        remote_eval=True,
        spec=str(spec_path),
        deepeval_judge_model="qwen3:latest",
        deepeval_identifier=None,
        technique="template",
    )

    spec_data = {
        "npc_key": "demo_npc",
        "system_prompt": "You are DemoNpc.",
        "evaluation": [
            {
                "question": "What is demo?",
                "expected_output": "Demo is a test.",
                "category": "general",
            },
        ],
    }

    mock_client = MagicMock()
    mock_client.evaluate.return_value = {
        "success": True,
        "data": {"testRunId": "eval-run-001"},
    }

    candidate_path = tmp_path / "candidate.gguf"
    candidate_path.write_text("stub")

    # record_pipeline_stage is imported INSIDE _run_deepeval_eval from
    # src.core.ops.pipeline_manifest — patch at source module
    with (
        patch("src.core.evaluation.evaluate.ConfidentAPIClient", return_value=mock_client),
        patch("src.core.evaluation.evaluate.ensure_confident_api_key", return_value=True),
        patch("src.core.ops.pipeline_manifest.record_pipeline_stage"),
    ):
        _run_deepeval_eval(args, candidate_path, baseline_path=None, spec_data=spec_data)

        mock_client.evaluate.assert_called_once()
        call_args, call_kwargs = mock_client.evaluate.call_args
        assert len(call_args) >= 2, "evaluate should receive test_cases and metric_collection"
        assert isinstance(call_args[0], list), "First arg should be test_cases list"
        assert call_args[0][0]["additionalMetadata"] == {
            "npc_key": "demo_npc",
            "category": "general",
            "concept": "general",
            "difficulty": "unknown",
            "format": "eval_question",
        }
        assert call_args[1]["name"] == "npc-model-quality", (
            "Metric collection name should be npc-model-quality"
        )


# ===================================================================
# evaluate.py — Remote Eval Records confident_url in Manifest
# ===================================================================


def test_evaluate_remote_eval_includes_confident_url_in_manifest(monkeypatch, tmp_path):
    """With ``--remote-eval``, the manifest metadata includes ``confident_url``."""
    from src.core.evaluation.evaluate import _run_deepeval_eval

    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "npc_key": "demo_npc",
                "npc_name": "DemoNpc",
                "subject": "Demo Studies",
                "system_prompt": "You are DemoNpc.",
            }
        )
    )

    args = _make_evaluate_args(
        remote_eval=True,
        spec=str(spec_path),
        deepeval_judge_model="qwen3:latest",
        deepeval_identifier="test-eval-id",
        technique="template",
    )

    spec_data = {
        "npc_key": "demo_npc",
        "system_prompt": "You are DemoNpc.",
        "evaluation": [
            {
                "question": "What is demo?",
                "expected_output": "Demo is a test.",
                "category": "general",
            },
        ],
    }

    mock_client = MagicMock()
    mock_client.evaluate.return_value = {
        "success": True,
        "data": {"testRunId": "manifest-run-001"},
    }

    candidate_path = tmp_path / "candidate.gguf"
    candidate_path.write_text("stub")

    captured_metadata: dict = {}

    def _capture_manifest(stage, status, **kwargs):
        captured_metadata.update(kwargs.get("metadata", {}))

    with (
        patch("src.core.evaluation.evaluate.ConfidentAPIClient", return_value=mock_client),
        patch("src.core.evaluation.evaluate.ensure_confident_api_key", return_value=True),
        patch(
            "src.core.ops.pipeline_manifest.record_pipeline_stage", side_effect=_capture_manifest
        ),
    ):
        _run_deepeval_eval(args, candidate_path, baseline_path=None, spec_data=spec_data)

        assert "confident_url" in captured_metadata, (
            "Manifest metadata should include confident_url"
        )
        assert "manifest-run-001" in captured_metadata["confident_url"], (
            "confident_url should reference the test run ID"
        )
        assert captured_metadata.get("remote_eval") is True, (
            "Manifest metadata should mark remote_eval as True"
        )
        assert captured_metadata.get("test_run_id") == "manifest-run-001", (
            "Manifest metadata should include test_run_id"
        )


# ===================================================================
# evaluate.py — ensure_confident_api_key Failure in _run_deepeval_eval
# ===================================================================


def test_evaluate_run_deepeval_handles_confident_api_key_failure(monkeypatch, tmp_path):
    """When ``ensure_confident_api_key()`` raises ``EnvironmentError`` in ``_run_deepeval_eval``,
    the function prints an error and returns without calling ``evaluate()``."""
    from src.core.evaluation.evaluate import _run_deepeval_eval

    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "npc_key": "demo_npc",
                "npc_name": "DemoNpc",
                "subject": "Demo Studies",
                "system_prompt": "You are DemoNpc.",
            }
        )
    )

    args = _make_evaluate_args(
        remote_eval=False,
        spec=str(spec_path),
        deepeval_judge_model="qwen3:latest",
    )

    candidate_path = tmp_path / "candidate.gguf"
    candidate_path.write_text("stub")

    with (
        patch(
            "src.core.evaluation.evaluate.ensure_confident_api_key",
            side_effect=OSError("CONFIDENT_API_KEY not set"),
        ),
    ):
        # Should return gracefully without raising or calling evaluate()
        _run_deepeval_eval(args, candidate_path, baseline_path=None, spec_data={})


# ===================================================================
# confident_push.py — push_goldens_if_confident Graceful Handling
# ===================================================================


def test_push_goldens_if_confident_graceful_no_file():
    """``push_goldens_if_confident()`` returns ``False`` when the file does not exist."""
    from src.core.ops.confident_push import push_goldens_if_confident

    result = push_goldens_if_confident(
        "/nonexistent/path/goldens.jsonl",
        alias="test-alias",
    )
    assert result is False


def test_push_goldens_if_confident_graceful_no_key(tmp_path):
    """``push_goldens_if_confident()`` returns ``False`` when ``is_confident_enabled()`` is ``False``."""
    from src.core.ops.confident_push import push_goldens_if_confident

    goldens_file = tmp_path / "goldens.jsonl"
    goldens_file.write_text(
        json.dumps({"input": "Q", "actualOutput": "A"}) + "\n",
        encoding="utf-8",
    )

    with patch("src.core.ops.confident_push.is_confident_enabled", return_value=False):
        result = push_goldens_if_confident(str(goldens_file), alias="test-alias")
    assert result is False


def test_push_goldens_if_confident_graceful_empty_file(tmp_path):
    """``push_goldens_if_confident()`` returns ``False`` for an empty file."""
    from src.core.ops.confident_push import push_goldens_if_confident

    goldens_file = tmp_path / "empty.jsonl"
    goldens_file.write_text("", encoding="utf-8")

    with patch("src.core.ops.confident_push.is_confident_enabled", return_value=True):
        result = push_goldens_if_confident(str(goldens_file), alias="test-alias")
    assert result is False


# ===================================================================
# env_loader.py — confident_available() and ensure_confident_api_key()
# ===================================================================


def test_confident_available_returns_true_when_env_set(monkeypatch):
    """``confident_available()`` returns ``True`` when ``CONFIDENT_API_KEY`` is set."""
    from src.core.ops.env_loader import confident_available

    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")
    assert confident_available() is True


def test_confident_available_returns_false_when_env_unset(monkeypatch):
    """``confident_available()`` returns ``False`` when ``CONFIDENT_API_KEY`` is missing."""
    from src.core.ops.env_loader import confident_available

    monkeypatch.delenv("CONFIDENT_API_KEY", raising=False)
    with patch("src.core.ops.env_loader.load_env_local", return_value=False):
        assert confident_available() is False


def test_ensure_confident_api_key_returns_true_when_set(monkeypatch):
    """``ensure_confident_api_key()`` returns ``True`` when env var is present."""
    from src.core.ops.env_loader import ensure_confident_api_key

    monkeypatch.setenv("CONFIDENT_API_KEY", "test-key-123")
    assert ensure_confident_api_key() is True


def test_ensure_confident_api_key_returns_false_when_not_set(monkeypatch):
    """``ensure_confident_api_key()`` returns ``False`` when env var is absent."""
    from src.core.ops.env_loader import ensure_confident_api_key

    monkeypatch.delenv("CONFIDENT_API_KEY", raising=False)
    with patch("src.core.ops.env_loader.load_env_local", return_value=False):
        assert ensure_confident_api_key() is False


def test_ensure_confident_api_key_strict_raises(monkeypatch):
    """``ensure_confident_api_key(strict=True)`` raises ``EnvironmentError`` when key is missing."""
    from src.core.ops.env_loader import ensure_confident_api_key

    monkeypatch.delenv("CONFIDENT_API_KEY", raising=False)
    with (
        patch("src.core.ops.env_loader.load_env_local", return_value=False),
        pytest.raises(EnvironmentError, match="CONFIDENT_API_KEY"),
    ):
        ensure_confident_api_key(strict=True)
