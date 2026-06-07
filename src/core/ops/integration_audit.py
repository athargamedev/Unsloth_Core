#!/usr/bin/env python3
"""Audit external integration readiness without exposing secrets."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_PATH = PROJECT_ROOT / "etc" / "npc-production-strategy.yaml"


@dataclass(frozen=True)
class IntegrationRequirement:
    enabled: bool
    required: bool


def audit_integrations(
    *, profile: str = "npc-production-grounded", root: str | Path | None = None
) -> dict[str, Any]:
    """Return report-safe integration health for a strategy profile.

    Credential checks report presence and source names only. Raw secret values
    must never leave the process through this payload.
    """

    project_root = Path(root or PROJECT_ROOT)
    requirements = _profile_requirements(profile, project_root)

    integrations = {
        "deepeval": _deepeval_status(requirements["deepeval"]),
        "confident": _credential_status(
            requirements["confident"],
            package_name="deepeval",
            env_names=("CONFIDENT_API_KEY", "DEEPEVAL_API_KEY"),
        ),
        "wandb": _credential_status(
            requirements["wandb"],
            package_name="wandb",
            env_names=("WANDB_API_KEY",),
            extra_sources=_wandb_sources(),
        ),
        "modal": _credential_status(
            requirements["modal"],
            package_name="modal",
            env_names=("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"),
            require_all_env=True,
        ),
    }

    interpreter = _interpreter_status(project_root)
    blockers = _blockers(integrations)
    return {
        "profile": profile,
        "ok": not blockers,
        "blockers": blockers,
        "integrations": integrations,
        "interpreter": interpreter,
    }


def format_integration_audit(payload: dict[str, Any]) -> str:
    """Render a compact human-readable integration audit."""

    lines = [
        "Integration audit",
        f"profile={payload.get('profile')}",
        f"ok={str(payload.get('ok')).lower()}",
    ]
    for name, status in (payload.get("integrations") or {}).items():
        version = status.get("package_version") or "missing"
        credential = status.get("credential_present")
        required = status.get("required")
        lines.append(
            f"- {name}: enabled={status.get('enabled')} required={required} "
            f"package={version} credential={credential}"
        )
        reason = status.get("unavailable_reason")
        if reason:
            lines.append(f"  reason: {reason}")
    blockers = payload.get("blockers") or []
    if blockers:
        lines.append("blockers:")
        for blocker in blockers:
            lines.append(f"- {blocker.get('integration')}: {blocker.get('reason')}")
    return "\n".join(lines)


def _profile_requirements(profile: str, project_root: Path) -> dict[str, IntegrationRequirement]:
    payload = yaml.safe_load((project_root / STRATEGY_PATH.relative_to(PROJECT_ROOT)).read_text()) or {}
    profiles = payload.get("profiles") or {}
    if profile not in profiles:
        raise ValueError(f"Unknown strategy profile: {profile}")
    profile_payload = profiles[profile] or {}
    quality_gate = profile_payload.get("quality_gate") or {}
    training = profile_payload.get("training") or {}
    runtime_eval = profile_payload.get("runtime_eval") or {}
    production = profile in {"npc-production-grounded", "npc-density-repair"}

    confident_enabled = bool(quality_gate.get("confident"))
    wandb_enabled = bool(
        quality_gate.get("wandb") or training.get("wandb") or runtime_eval.get("wandb")
    )
    return {
        "deepeval": IntegrationRequirement(enabled=True, required=production),
        "confident": IntegrationRequirement(
            enabled=confident_enabled,
            required=production and confident_enabled,
        ),
        "wandb": IntegrationRequirement(enabled=wandb_enabled, required=production and wandb_enabled),
        "modal": IntegrationRequirement(enabled=False, required=False),
    }


def _deepeval_status(requirement: IntegrationRequirement) -> dict[str, Any]:
    package_version = _package_version("deepeval")
    cli_path = shutil.which("deepeval")
    available = package_version is not None
    return {
        "enabled": requirement.enabled,
        "required": requirement.required,
        "package": "deepeval",
        "package_version": package_version,
        "cli_present": cli_path is not None,
        "credential_present": _any_env(("CONFIDENT_API_KEY", "DEEPEVAL_API_KEY")),
        "credential_sources": _env_sources(("CONFIDENT_API_KEY", "DEEPEVAL_API_KEY")),
        "available": available,
        "unavailable_reason": None if available else "deepeval package is not installed",
    }


def _credential_status(
    requirement: IntegrationRequirement,
    *,
    package_name: str,
    env_names: tuple[str, ...],
    require_all_env: bool = False,
    extra_sources: list[str] | None = None,
) -> dict[str, Any]:
    package_version = _package_version(package_name)
    sources = [*_env_sources(env_names), *(extra_sources or [])]
    env_present = _all_env(env_names) if require_all_env else _any_env(env_names)
    credential_present = bool(env_present or extra_sources)
    available = package_version is not None and (credential_present or not requirement.required)
    reason = None
    if package_version is None:
        reason = f"{package_name} package is not installed"
    elif requirement.required and not credential_present:
        reason = f"required credential missing: {' + '.join(env_names)}"

    return {
        "enabled": requirement.enabled,
        "required": requirement.required,
        "package": package_name,
        "package_version": package_version,
        "cli_present": shutil.which(package_name) is not None,
        "credential_present": credential_present,
        "credential_sources": sources,
        "available": available,
        "unavailable_reason": reason,
    }


def _interpreter_status(project_root: Path) -> dict[str, Any]:
    pyenv_file = project_root / ".python-version"
    expected = pyenv_file.read_text(encoding="utf-8").strip() if pyenv_file.exists() else None
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return {
        "executable": sys.executable,
        "version": current,
        "python_version_file": expected,
        "matches_python_version_file": expected is None or current.startswith(expected),
    }


def _blockers(integrations: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for name, status in integrations.items():
        if status.get("required") and not status.get("available"):
            blockers.append(
                {
                    "integration": name,
                    "reason": str(status.get("unavailable_reason") or "required integration unavailable"),
                }
            )
    return blockers


def _package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def _any_env(names: tuple[str, ...]) -> bool:
    return any(bool(os.environ.get(name)) for name in names)


def _all_env(names: tuple[str, ...]) -> bool:
    return all(bool(os.environ.get(name)) for name in names)


def _env_sources(names: tuple[str, ...]) -> list[str]:
    return [f"env:{name}" for name in names if os.environ.get(name)]


def _wandb_sources() -> list[str]:
    netrc = Path.home() / ".netrc"
    if not netrc.exists():
        return []
    try:
        text = netrc.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return ["netrc:wandb.ai"] if "api.wandb.ai" in text or "wandb.ai" in text else []
