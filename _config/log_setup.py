"""
_config/log_setup.py — Structured logging for Unsloth_Core scripts.

Provides a consistent logging setup across all pipeline scripts:
- Timestamped, leveled output to stderr
- JSON state lines to stdout for frontend/machine consumption

Usage:
    from _config.log_setup import log_info, log_warn, log_error, log_state

    log_info("Loading model...")
    log_warn("Low VRAM: %s GB", vram)
    log_error("Training failed: %s", exc)
    log_state("training_step", run_id="abc123", loss=0.05, step=100)
"""

import json
import logging
import sys
from datetime import datetime, timezone


def _make_logger(name: str = "ucore", level: int = logging.INFO) -> logging.Logger:
    """Create or retrieve a configured logger with consistent format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


# Module-level convenience wrappers so scripts can do:
#   from _config.log_setup import log_info, log_state

_log = _make_logger()


def log_info(msg: str, *args) -> None:
    _log.info(msg, *args)


def log_warn(msg: str, *args) -> None:
    _log.warning(msg, *args)


def log_error(msg: str, *args) -> None:
    _log.error(msg, *args)


def log_state(event: str, **kwargs) -> None:
    """Emit a structured JSON state line to stdout.

    This is separate from human-readable logging to stderr.
    The frontend dashboard can consume these lines for progress tracking.
    """
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def set_log_level(level: int) -> None:
    """Change the log level at runtime (e.g., set_log_level(logging.DEBUG))."""
    _log.setLevel(level)
    for h in _log.handlers:
        h.setLevel(level)
