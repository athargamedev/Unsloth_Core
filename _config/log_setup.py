"""
_config/log_setup.py — Structured logging for Unsloth_Core scripts.

Provides a consistent logging setup across all pipeline scripts:
- Timestamped, leveled output to stderr
- JSON state lines to stdout for frontend/machine consumption
- Persistent JSON events to .pipeline/runs/{run_id}/log_state.jsonl
  when a pipeline run is active (see set_active_run()).

Usage:
    from _config.log_setup import log_info, log_warn, log_error, log_state
    from _config.log_setup import set_active_run, clear_active_run

    log_info("Loading model...")
    log_warn("Low VRAM: %s GB", vram)
    log_error("Training failed: %s", exc)
    log_state("training_step", run_id="abc123", loss=0.05, step=100)

    # Activate persistent logging after RunRegistry.start_run():
    run_dir = registry.start_run(...)
    set_active_run(run_id, run_dir)
    # ... pipeline work; all log_state() calls now also write to log_state.jsonl ...
    clear_active_run()
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


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

    Separate from human-readable logging to stderr.
    The frontend dashboard consumes these lines for progress tracking.

    When a pipeline run is active (registered via set_active_run()), the same
    payload is also appended to .pipeline/runs/{run_id}/log_state.jsonl for
    permanent structured storage — the unified source of truth for run events.
    """
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()

    # Persist to run-dir when an active run has been registered
    if _active_run_dir is not None:
        try:
            p = _active_run_dir / "log_state.jsonl"
            with p.open("a", encoding="utf-8") as f:
                json.dump(payload, f, default=str)
                f.write("\n")
        except Exception:
            pass  # Best-effort — never break the pipeline


def set_log_level(level: int) -> None:
    """Change the log level at runtime (e.g., set_log_level(logging.DEBUG))."""
    _log.setLevel(level)
    for h in _log.handlers:
        h.setLevel(level)


# ── Active run context ────────────────────────────────────────────────────────
# Set by pipeline scripts after calling RunRegistry.start_run() so that
# log_state() can persist events to the per-run log_state.jsonl file.

_active_run_id: str | None = None
_active_run_dir: Path | None = None


def set_active_run(run_id: str, run_dir: Path) -> None:
    """Register the active pipeline run so log_state() can persist to it.

    Call this immediately after RunRegistry.start_run() returns a run_dir.

    Args:
        run_id:  The canonical pipeline run ID
                 (e.g. '20260520_history_guide_train_fast-3b_001').
        run_dir: Path to .pipeline/runs/{run_id}/ returned by
                 RunRegistry.start_run().
    """
    global _active_run_id, _active_run_dir
    _active_run_id = run_id
    _active_run_dir = run_dir


def clear_active_run() -> None:
    """Unregister the active run. Call at the end of a pipeline stage."""
    global _active_run_id, _active_run_dir
    _active_run_id = None
    _active_run_dir = None


def get_active_run_id() -> str | None:
    """Return the currently active pipeline run ID, or None."""
    return _active_run_id


def get_active_run_dir() -> Path | None:
    """Return the currently active run_dir, or None."""
    return _active_run_dir
