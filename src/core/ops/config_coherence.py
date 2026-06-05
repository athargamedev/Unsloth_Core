#!/usr/bin/env python3
"""Project-wide configuration coherence audit for Unsloth_Core.

This module catches contradictions that can make expensive NPC runs unsafe:
production profiles using smoke/template paths, LoRA alpha/rank drift, missing
response-only masking, and stale hardcoded quick-eval defaults.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

APPROVED_PRODUCTION_TECHNIQUES = {"ollama", "docs", "openai", "anthropic"}
SMOKE_ONLY_TECHNIQUES = {"template"}

REQUIRED_TRAINING_INVARIANTS = {
    "train_on_responses_only": True,
    "packing_for_6gb": False,
}

LORA_STABILITY_POLICY = {
    "default": "alpha_eq_r",
    "allow_override_if_named_experiment": True,
}


def audit_config_coherence(root: str | Path | None = None) -> dict[str, Any]:
    """Return structured config-coherence audit results for a project root."""

    project_root = Path(root or Path(__file__).resolve().parents[3])
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    _audit_strategy_profiles(project_root, failures, warnings)
    _audit_parameter_registry(project_root, failures, warnings)
    _audit_presets(project_root, failures, warnings)
    _audit_quick_eval(project_root, failures, warnings)

    return {"ok": not failures, "failures": failures, "warnings": warnings}


def format_audit_table(result: dict[str, Any]) -> str:
    """Human-readable audit summary for CLI output."""

    lines = ["Config coherence audit", f"ok={str(result.get('ok')).lower()}"]
    failures = result.get("failures") or []
    warnings = result.get("warnings") or []
    if failures:
        lines.append("failures:")
        for failure in failures:
            lines.append(
                f"- {failure.get('file')}::{failure.get('path')} "
                f"{failure.get('reason')} (expected={failure.get('expected')!r}, actual={failure.get('actual')!r})"
            )
    if warnings:
        lines.append("warnings:")
        for warning in warnings:
            lines.append(f"- {warning.get('file')}::{warning.get('path')} {warning.get('reason')}")
    if not failures and not warnings:
        lines.append("no failures or warnings")
    return "\n".join(lines)


def _audit_strategy_profiles(project_root: Path, failures: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    path = project_root / "etc" / "npc-production-strategy.yaml"
    data = _read_yaml(path)
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict):
        warnings.append(_issue(path, "profiles", "npc production strategy missing profiles map", expected="mapping", actual=type(profiles).__name__))
        return

    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        technique = profile.get("technique")
        dataset = profile.get("dataset") or {}
        training = profile.get("training") or {}
        is_production = _is_production_profile(profile_name, profile)
        if not is_production:
            continue

        if technique in SMOKE_ONLY_TECHNIQUES:
            failures.append(
                _issue(
                    path,
                    f"profiles.{profile_name}.technique",
                    "production profile cannot use smoke-only template technique",
                    expected=f"one of {sorted(APPROVED_PRODUCTION_TECHNIQUES)}",
                    actual=technique,
                )
            )
        if dataset.get("template_allowed") is not False:
            failures.append(
                _issue(
                    path,
                    f"profiles.{profile_name}.dataset.template_allowed",
                    "production profile must not allow template datasets",
                    expected=False,
                    actual=dataset.get("template_allowed"),
                )
            )
        _audit_training_block(path, f"profiles.{profile_name}.training", training, failures)


def _audit_parameter_registry(project_root: Path, failures: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    path = project_root / "etc" / "parameter-registry.yaml"
    data = _read_yaml(path)
    params = data.get("parameters") if isinstance(data, dict) else {}
    lora_r = params.get("lora_r") if isinstance(params, dict) else {}
    lora_alpha = params.get("lora_alpha") if isinstance(params, dict) else {}
    if not isinstance(lora_alpha, dict):
        return

    tooltip = str(lora_alpha.get("tooltip") or "")
    default_alpha = lora_alpha.get("default")
    default_r = lora_r.get("default") if isinstance(lora_r, dict) else None
    if re.search(r"2\s*x\s*lora_r|2x\s+lora_r|alpha\s*=\s*2r", tooltip, flags=re.IGNORECASE):
        failures.append(
            _issue(
                path,
                "parameters.lora_alpha.tooltip",
                "parameter registry must not describe alpha=2r as normal production policy",
                expected="alpha equals rank unless experimental",
                actual=tooltip,
            )
        )
    if default_r is not None and default_alpha != default_r:
        failures.append(
            _issue(
                path,
                "parameters.lora_alpha.default",
                "default LoRA alpha must equal default rank unless experimental",
                expected=default_r,
                actual=default_alpha,
            )
        )


def _audit_presets(project_root: Path, failures: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    presets_dir = project_root / "etc" / "presets"
    if not presets_dir.exists():
        return
    for path in sorted(presets_dir.glob("*.yaml")):
        data = _read_yaml(path)
        if not isinstance(data, dict):
            continue
        lora = data.get("lora") or {}
        training = data.get("training") or {}
        if not _is_production_preset(path, data):
            continue
        if isinstance(lora, dict) and "r" in lora and "alpha" in lora:
            if lora.get("alpha") != lora.get("r") and not _has_experimental_lora_override(data):
                failures.append(
                    _issue(
                        path,
                        "lora.alpha",
                        "preset LoRA alpha must equal rank unless experimental",
                        expected=lora.get("r"),
                        actual=lora.get("alpha"),
                    )
                )
        if True:
            if training.get("train_on_responses_only") is not True:
                failures.append(
                    _issue(
                        path,
                        "training.train_on_responses_only",
                        "production preset must use response-only masking",
                        expected=True,
                        actual=training.get("train_on_responses_only"),
                    )
                )
            if training.get("packing") is not False:
                failures.append(
                    _issue(
                        path,
                        "training.packing",
                        "6GB-safe production preset must disable packing",
                        expected=False,
                        actual=training.get("packing"),
                    )
                )


def _audit_quick_eval(project_root: Path, failures: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    path = project_root / "src" / "core" / "evaluation" / "quick_eval.py"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if re.search(r"lora_alpha\s*=\s*32", text) and not re.search(
        r"smoke[-_ ]only|experimental_lora_scaling|config-driven", text, flags=re.IGNORECASE
    ):
        failures.append(
            _issue(
                path,
                "load_model.lora_alpha",
                "hardcoded lora_alpha=32 must be smoke-only, experimental, or config-driven",
                expected="config-driven or alpha=rank",
                actual="lora_alpha=32",
            )
        )


def _audit_training_block(path: Path, prefix: str, training: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    r = training.get("lora_r")
    alpha = training.get("lora_alpha")
    if r is not None and alpha is not None and alpha != r and not _has_experimental_lora_override(training):
        failures.append(
            _issue(
                path,
                f"{prefix}.lora_alpha",
                "production LoRA alpha must equal rank unless experimental",
                expected=r,
                actual=alpha,
            )
        )
    if training.get("train_on_responses_only") is not True:
        failures.append(
            _issue(
                path,
                f"{prefix}.train_on_responses_only",
                "production training must use response-only masking",
                expected=True,
                actual=training.get("train_on_responses_only"),
            )
        )
    if training.get("packing") is not False:
        failures.append(
            _issue(
                path,
                f"{prefix}.packing",
                "6GB-safe production training must disable packing",
                expected=False,
                actual=training.get("packing"),
            )
        )


def _is_production_profile(name: str, profile: dict[str, Any]) -> bool:
    dataset = profile.get("dataset") or {}
    if dataset.get("production_allowed") is False:
        return False
    if profile.get("technique") in SMOKE_ONLY_TECHNIQUES:
        return "production" in name
    return True


def _is_production_preset(path: Path, data: dict[str, Any]) -> bool:
    name = path.stem
    if name in {"smoke", "safe-any", "wandb", "wandb_compare"}:
        return False
    if name.startswith("remote-") or name.endswith("-8b"):
        return False
    metadata = data.get("metadata") or {}
    if metadata.get("smoke_only") is True:
        return False
    if _has_experimental_lora_override(data):
        return False
    return bool(data.get("lora") or data.get("training"))


def _has_experimental_lora_override(data: dict[str, Any]) -> bool:
    metadata = data.get("metadata") if isinstance(data, dict) else None
    return bool(isinstance(metadata, dict) and metadata.get("experimental_lora_scaling") is True)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _issue(path: Path, path_key: str, reason: str, *, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "file": str(path),
        "path": path_key,
        "expected": expected,
        "actual": actual,
        "reason": reason,
    }


if __name__ == "__main__":
    result = audit_config_coherence()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
