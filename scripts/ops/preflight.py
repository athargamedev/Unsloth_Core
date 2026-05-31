#!/usr/bin/env python3
"""Preflight checks for local Unsloth_Core pipeline stages.

This module centralizes the checks we want before expensive training or
DeepEval runs:
- GPU memory inventory via nvidia-smi
- Optional Ollama unload to free VRAM
- GCC toolchain availability for training
- Automatic preset downgrade for low-VRAM training runs

The module can be imported by the training / dataset-eval launchers and also
run as a standalone CLI for inspection.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.env_loader import confident_available
from scripts.ops.ollama_lifecycle import list_running_ollama_models, stop_running_models
from scripts.ops.model_presets import DEFAULT_FALLBACK_PRESET


@dataclass
class PreflightReport:
    phase: str
    preset_requested: str | None = None
    preset_effective: str | None = None
    technique: str | None = None
    total_vram_gb: float | None = None
    free_vram_gb: float | None = None
    gcc_ok: bool = False
    gcc_path: str | None = None
    running_ollama_models: list[str] = field(default_factory=list)
    stopped_ollama_models: list[str] = field(default_factory=list)
    recommendation: dict[str, Any] = field(default_factory=dict)
    confident_available: bool = False
    confident_warning: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "blocked"
        if self.warnings:
            return "degraded"
        return "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "preset_requested": self.preset_requested,
            "preset_effective": self.preset_effective,
            "technique": self.technique,
            "total_vram_gb": self.total_vram_gb,
            "free_vram_gb": self.free_vram_gb,
            "gcc_ok": self.gcc_ok,
            "gcc_path": self.gcc_path,
            "running_ollama_models": self.running_ollama_models,
            "stopped_ollama_models": self.stopped_ollama_models,
            "recommendation": self.recommendation,
            "confident_available": self.confident_available,
            "confident_warning": self.confident_warning,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _parse_gpu_memory_csv(output: str) -> tuple[float | None, float | None]:
    """Return the largest (free, total) GPU pair from nvidia-smi output."""
    best_free: float | None = None
    best_total: float | None = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            free = float(parts[0])
            total = float(parts[1])
        except ValueError:
            continue
        if best_total is None or total > best_total:
            best_free = free
            best_total = total
    if best_total is None:
        return None, None
    return best_free, best_total


def query_gpu_memory() -> tuple[float | None, float | None]:
    """Query free/total VRAM in GiB using nvidia-smi.

    Returns (free_gb, total_gb) or (None, None) when unavailable.
    """
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return None, None
    except subprocess.TimeoutExpired:
        return None, None

    if completed.returncode != 0:
        return None, None

    free_mb, total_mb = _parse_gpu_memory_csv(completed.stdout)
    if total_mb is None:
        return None, None
    return round(free_mb / 1024.0, 2) if free_mb is not None else None, round(total_mb / 1024.0, 2)


def check_gcc() -> tuple[bool, str | None, str | None]:
    """Check that gcc exists and can report its version."""
    gcc_path = shutil.which("gcc")
    if not gcc_path:
        return False, None, "gcc not found in PATH"

    try:
        completed = subprocess.run(
            [gcc_path, "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, gcc_path, "gcc --version timed out"

    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "gcc --version failed").strip()
        return False, gcc_path, stderr

    return True, gcc_path, None


def _check_confident() -> tuple[bool, str | None]:
    """Check whether Confident AI credentials are configured for DeepEval."""
    available = confident_available()
    if not available:
        return (
            False,
            "CONFIDENT_API_KEY not set. DeepEval results will NOT be uploaded to "
            "Confident AI dashboard. Set CONFIDENT_API_KEY in .env.local or run "
            "'deepeval login'.",
        )
    return True, None


def _maybe_recommend_preset(
    *,
    spec_path: Path | None,
    preset: str | None,
    total_vram_gb: float | None,
) -> tuple[str | None, dict[str, Any]]:
    """Return a likely-effective preset and the underlying workload recommendation."""
    if not preset:
        return None, {}

    recommendation: dict[str, Any] = {}
    effective_preset = preset

    if not spec_path or not spec_path.exists():
        # Fallback heuristic for local runs without a spec: low-VRAM fast-3b -> safe-any.
        if preset == "fast-3b" and total_vram_gb is not None and total_vram_gb < 10.0:
            effective_preset = DEFAULT_FALLBACK_PRESET
            recommendation = {
                "training": {
                    "location": "remote_colab",
                    "reason": f"Local VRAM {total_vram_gb}GB is below the fast-3b safety floor; use {DEFAULT_FALLBACK_PRESET}",
                }
            }
        return effective_preset, recommendation

    try:
        with spec_path.open("r", encoding="utf-8") as f:
            spec = json.load(f)
    except Exception as exc:
        recommendation = {"training": {"location": "unknown", "reason": f"Could not load spec: {exc}"}}
        return effective_preset, recommendation

    try:
        from scripts.orchestration.plan_execution import recommend

        plan = recommend(spec, preset, total_vram_gb)
        recommendation = plan.get("recommendation", {})
        training = recommendation.get("training", {}) or {}
        if preset == "fast-3b" and training.get("location") == "remote_colab":
            effective_preset = DEFAULT_FALLBACK_PRESET
    except Exception as exc:
        recommendation = {"training": {"location": "unknown", "reason": f"Plan evaluation failed: {exc}"}}

    return effective_preset, recommendation


def run_preflight(
    *,
    phase: str,
    preset: str | None = None,
    spec_path: str | Path | None = None,
    technique: str | None = None,
    ollama_url: str = "http://localhost:11434",
    auto_unload_ollama: bool = True,
    require_gcc: bool | None = None,
) -> PreflightReport:
    """Run a stage-appropriate preflight check and return a structured report."""
    report = PreflightReport(
        phase=phase,
        preset_requested=preset,
        preset_effective=preset,
        technique=technique,
    )

    free_vram_gb, total_vram_gb = query_gpu_memory()
    report.free_vram_gb = free_vram_gb
    report.total_vram_gb = total_vram_gb

    running = list_running_ollama_models(ollama_url)
    report.running_ollama_models = running
    if running and auto_unload_ollama:
        stopped = stop_running_models(ollama_url)
        report.stopped_ollama_models = stopped
        if stopped:
            report.warnings.append(
                f"Stopped Ollama model(s) before {phase}: {', '.join(stopped)}"
            )
    elif running:
        report.warnings.append(
            f"Ollama model(s) still loaded before {phase}: {', '.join(running)}"
        )

    if require_gcc is None:
        require_gcc = phase == "train"
    if require_gcc:
        gcc_ok, gcc_path, gcc_error = check_gcc()
        report.gcc_ok = gcc_ok
        report.gcc_path = gcc_path
        if not gcc_ok:
            report.errors.append(gcc_error or "gcc check failed")
    else:
        report.gcc_ok = True

    confident_ok, confident_msg = _check_confident()
    report.confident_available = confident_ok
    report.confident_warning = confident_msg
    if not confident_ok and confident_msg:
        report.warnings.append(confident_msg)

    effective_preset, recommendation = _maybe_recommend_preset(
        spec_path=Path(spec_path) if spec_path else None,
        preset=preset,
        total_vram_gb=total_vram_gb,
    )
    if preset == "fast-3b" and total_vram_gb is not None and total_vram_gb < 10.0:
        effective_preset = DEFAULT_FALLBACK_PRESET
    report.preset_effective = effective_preset
    report.recommendation = recommendation

    if preset == "fast-3b" and effective_preset == DEFAULT_FALLBACK_PRESET:
        report.warnings.append(
            f"Auto-fallback: {preset} -> {effective_preset} on this GPU"
        )

    if total_vram_gb is None:
        report.warnings.append("Could not read GPU memory via nvidia-smi")
    elif free_vram_gb is not None and free_vram_gb < 2.0:
        report.warnings.append(f"Only {free_vram_gb:.2f} GiB free VRAM remains")

    return report


def _format_text_report(report: PreflightReport) -> str:
    lines = [
        f"Preflight status: {report.status}",
        f"Phase:            {report.phase}",
        f"Preset:           {report.preset_requested or '-'} -> {report.preset_effective or '-'}",
        f"Technique:        {report.technique or '-'}",
        f"VRAM free/total:  {report.free_vram_gb if report.free_vram_gb is not None else '?'} / {report.total_vram_gb if report.total_vram_gb is not None else '?'} GiB",
        f"gcc:              {report.gcc_path or '-'} ({'ok' if report.gcc_ok else 'missing'})",
        f"Confident AI:     {'ok' if report.confident_available else 'missing'}",
        f"Running Ollama:   {', '.join(report.running_ollama_models) if report.running_ollama_models else '-'}",
        f"Stopped Ollama:   {', '.join(report.stopped_ollama_models) if report.stopped_ollama_models else '-'}",
    ]
    if report.recommendation:
        training = report.recommendation.get("training", {}) or {}
        if training:
            lines.append(f"Training recommendation: {training.get('location', '-')}: {training.get('reason', '-')}")
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a preflight check for the Unsloth_Core pipeline")
    parser.add_argument("--phase", default="train", choices=["train", "dataset_eval", "export"], help="Pipeline phase")
    parser.add_argument("--preset", help="Requested training preset")
    parser.add_argument("--spec", help="Subject spec JSON path")
    parser.add_argument("--technique", help="Dataset technique name")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama server URL")
    parser.add_argument("--no-auto-unload-ollama", action="store_true", help="Do not stop running Ollama models")
    parser.add_argument("--no-gcc-check", action="store_true", help="Skip gcc validation even for training")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    report = run_preflight(
        phase=args.phase,
        preset=args.preset,
        spec_path=args.spec,
        technique=args.technique,
        ollama_url=args.ollama_url,
        auto_unload_ollama=not args.no_auto_unload_ollama,
        require_gcc=False if args.no_gcc_check else None,
    )

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(_format_text_report(report))

    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
