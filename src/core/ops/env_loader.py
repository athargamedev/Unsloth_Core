#!/usr/bin/env python3
"""Environment variable loader and validator for external service credentials.

Automatically sources ``.env.local`` from the project root on module import,
so callers can rely on ``ensure_confident_api_key()`` without manual setup.

# Limitations: This custom parser does NOT support:
# - Escaped characters (\\", \\n)
# - Multi-line quoted values
# - ${VARIABLE} substitution
# For complex .env files, consider using python-dotenv.
"""

from __future__ import annotations

import os

__all__ = ["confident_available", "ensure_confident_api_key"]

_ENV_LOADED: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_project_root() -> str | None:
    """Walk up from this file's directory to find the project root (has ``.git``)."""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):  # safety limit against infinite loop
        if os.path.isdir(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse a single ``.env``-format line into ``(key, value)``.

    Handles ``KEY=VALUE``, ``KEY='value'``, and ``KEY="value"`` formats.
    Returns ``None`` for blank lines, comment lines, or malformed lines.

    Limitations: This custom parser does NOT support:
    - Escaped characters (\\", \\n)
    - Multi-line quoted values
    - ${VARIABLE} substitution
    For complex .env files, consider using python-dotenv.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None

    key, _, rest = stripped.partition("=")
    key = key.strip()
    if not key:
        return None

    value = rest.strip()
    # Strip matching surrounding quotes
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]

    return (key, value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_env_local() -> bool:
    """Find and load ``.env.local`` from the project root into ``os.environ``.

    Only sets variables that are **not** already present in the environment,
    so externally-set values always take precedence.

    Returns ``True`` if at least one new variable was loaded.
    """
    project_root = _find_project_root()
    if project_root is None:
        return False

    env_path = os.path.join(project_root, ".env.local")
    if not os.path.isfile(env_path):
        return False

    loaded = 0
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            parsed = _parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            if key not in os.environ:
                os.environ[key] = value
                loaded += 1

    return loaded > 0


def _auto_source_env_local() -> bool:
    """Called once on module import; idempotent thereafter.

    Uses the module-level ``_ENV_LOADED`` flag to guarantee a single load
    regardless of how many times it is invoked.
    """
    global _ENV_LOADED  # noqa: PLW0603  -- intentional module-level flag
    if _ENV_LOADED:
        return True
    _ENV_LOADED = True
    return load_env_local()


def confident_available() -> bool:
    """Check whether Confident AI credentials are configured.

    Returns ``True`` if ``CONFIDENT_API_KEY`` is set in the environment.
    Does **not** verify the key is valid — only that it is present.
    """
    return bool(os.environ.get("CONFIDENT_API_KEY"))


def ensure_confident_api_key(strict: bool = False) -> bool:
    """Ensure ``CONFIDENT_API_KEY`` is available, loading ``.env.local`` first.

    Parameters
    ----------
    strict : bool
        When ``True``, raises ``EnvironmentError`` if the key is missing.
        When ``False`` (default), returns ``True`` / ``False`` silently.

    Returns
    -------
    bool
        ``True`` if ``CONFIDENT_API_KEY`` is present in the environment
        after attempting to load ``.env.local``, ``False`` otherwise.
    """
    # Attempt to source .env.local (idempotent via _ENV_LOADED flag)
    _auto_source_env_local()

    available = confident_available()
    if not available and strict:
        raise OSError(
            "CONFIDENT_API_KEY environment variable is not set.\n"
            "  Export it:  export CONFIDENT_API_KEY='your-key-here'\n"
            "  Or log in:  deepeval login\n"
            "  Get a key:  https://app.confident-ai.com/profile"
        )
    return available


# Auto-source .env.local on module import so any consumer gets it for free.
_auto_source_env_local()
