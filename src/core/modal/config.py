"""Modal config — reads etc/modal/config.yaml and provides a gated guard.

Usage:
    from src.core.modal.config import require_modal, modal_enabled
    if modal_enabled():
        # run Modal operation
        pass
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MODAL_CONFIG_PATH = _PROJECT_ROOT / "etc" / "modal" / "config.yaml"

# Lazy-loaded so import doesn't fail when yaml isn't installed
_config: dict | None = None


def _load_config() -> dict:
    global _config
    if _config is not None:
        return _config
    try:
        import yaml

        if _MODAL_CONFIG_PATH.exists():
            _config = yaml.safe_load(_MODAL_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        else:
            _config = {}
    except Exception:
        _config = {}
    return _config or {}


def modal_enabled() -> bool:
    """Return True if Modal is enabled in config.yaml AND credentials are set."""
    cfg = _load_config()
    if not cfg.get("enabled", False):
        return False
    token_id = os.getenv("MODAL_TOKEN_ID") or os.getenv(
        cfg.get("credentials", {}).get("token_id_env", "MODAL_TOKEN_ID")
    )
    token_secret = os.getenv("MODAL_TOKEN_SECRET") or os.getenv(
        cfg.get("credentials", {}).get("token_secret_env", "MODAL_TOKEN_SECRET")
    )
    return bool(token_id and token_secret)


def require_modal() -> None:
    """Raise RuntimeError if Modal is not configured and enabled."""
    if not modal_enabled():
        cfg = _load_config()
        gate = cfg.get("activation_gate", "Modal is not enabled")
        raise RuntimeError(
            f"Modal is not available. {gate}. "
            "Set enabled: true in etc/modal/config.yaml and ensure "
            "MODAL_TOKEN_ID + MODAL_TOKEN_SECRET are in the environment."
        )


def get_config() -> dict:
    """Return the full Modal config dict (read-only)."""
    return _load_config()
