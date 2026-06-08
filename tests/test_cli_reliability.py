from __future__ import annotations

import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_ucore():
    ucore_path = PROJECT_ROOT / "src/cli/ucore"
    loader = importlib.machinery.SourceFileLoader("ucore_cli_reliability", str(ucore_path))
    spec = importlib.util.spec_from_loader("ucore_cli_reliability", loader, origin=str(ucore_path))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ucore_path)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ucore_requires_a_command():
    result = subprocess.run(["./ucore"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "usage:" in result.stderr.lower()


def test_ucore_rejects_conflicting_generate_modes():
    result = subprocess.run(
        [
            "./ucore",
            "generate",
            "data/npcs/specs/history_guide.json",
            "--ollama",
            "--technique",
            "template",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "not allowed with argument" in result.stderr


def test_ucore_generate_ollama_default_model_is_current_project_default():
    result = subprocess.run(
        ["./ucore", "generate-ollama", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "qwen2.5:7b" in result.stdout
    assert "llama3.1-3060-chat" not in result.stdout


def test_ucore_pipeline_ollama_uses_optimized_generator(monkeypatch):
    ucore = load_ucore()
    captured: list[list[str]] = []

    def fake_run_cmd(cmd, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr(ucore, "run_cmd", fake_run_cmd)

    ucore.main(
        [
            "pipeline",
            "data/npcs/specs/history_guide.json",
            "--ollama",
            "--skip-spec-validate",
            "--skip-dataset-eval",
            "--skip-smoke",
            "--skip-eval",
        ]
    )

    rendered = [" ".join(cmd) for cmd in captured]
    assert any(
        "generate_dataset.py" in cmd and "_generate_shared.py" not in cmd for cmd in rendered
    )
    assert not any("_generate_shared.py" in cmd for cmd in rendered)


def test_train_export_uses_src_core_export_after_scripts_symlink_removal():
    train_source = (PROJECT_ROOT / "src" / "core" / "training" / "train.py").read_text(
        encoding="utf-8"
    )

    assert 'PROJECT_ROOT / "src" / "core" / "export" / "export.py"' in train_source
    assert 'PROJECT_ROOT / "scripts" / "export" / "export.py"' not in train_source


def test_ucore_generate_ollama_preserves_zero_values(monkeypatch):
    ucore = load_ucore()
    captured: list[list[str]] = []

    def fake_run_cmd(cmd, **kwargs):
        captured.append(cmd)

    monkeypatch.setattr(ucore, "run_cmd", fake_run_cmd)

    ucore.main(
        [
            "generate-ollama",
            "data/npcs/specs/history_guide.json",
            "--batch-size",
            "0",
            "--max-retries",
            "0",
            "--temperature",
            "0",
            "--multi-turn-ratio",
            "0",
            "--seed",
            "0",
            "--val-split",
            "0",
        ]
    )

    assert captured
    cmd = captured[0]
    assert cmd[cmd.index("--batch-size") + 1] == "0"
    assert cmd[cmd.index("--max-retries") + 1] == "0"
    assert cmd[cmd.index("--temperature") + 1] == "0.0"
    assert cmd[cmd.index("--multi-turn-ratio") + 1] == "0.0"
    assert cmd[cmd.index("--seed") + 1] == "0"
    assert cmd[cmd.index("--val-split") + 1] == "0.0"


def test_pipeline_sanitize_command_requires_strict_canonical_and_complete_metadata():
    ucore = load_ucore()

    cmd = ucore.build_pipeline_sanitize_cmd(
        "data/datasets/history_guide/ollama/train.jsonl",
        "data/datasets/history_guide/ollama/train_clean.jsonl",
    )

    assert "--strict-canonical" in cmd
    assert "--require-complete-metadata" in cmd


def test_pipeline_sanitize_command_dev_metadata_repair_opt_out():
    ucore = load_ucore()

    cmd = ucore.build_pipeline_sanitize_cmd(
        "data/datasets/history_guide/template/train.jsonl",
        "data/datasets/history_guide/template/train_clean.jsonl",
        allow_metadata_repair=True,
    )

    assert "--strict-canonical" in cmd
    assert "--require-complete-metadata" not in cmd


def test_pipeline_metadata_repair_opt_out_is_template_only(monkeypatch):
    ucore = load_ucore()

    def fail_run_cmd(cmd, **kwargs):  # pragma: no cover - parser should stop first
        raise AssertionError(f"unexpected command execution: {cmd}")

    monkeypatch.setattr(ucore, "run_cmd", fail_run_cmd)

    try:
        ucore.main(
            [
                "pipeline",
                "data/npcs/specs/history_guide.json",
                "--technique",
                "ollama",
                "--allow-metadata-repair",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("expected parser error")
