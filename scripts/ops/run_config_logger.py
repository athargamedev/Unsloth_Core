#!/usr/bin/env python3
"""Run configuration audit trail.

Records every resolved parameter value for each pipeline run.
Writes human-readable YAML to output dir + JSON for machine parsing
+ JSONB snapshot to DB (best-effort).

Usage:
    from scripts.ops.run_config_logger import log_run_config

    log_run_config(
        npc_key="history_guide",
        stage="training",
        output_dir="outputs/history_guide/runs/run_20260529_120000",
        resolved_params=resolved_params_dict,
        preflight_report=preflight.as_dict(),  # optional
    )

The audit trail creates two files in the output directory:
  - run_config.yaml  — human-readable YAML
  - run_config.json  — machine-parseable JSON (same data)

And best-effort writes to the pipeline_config_snapshots DB table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from scripts.ops.pipeline_db import PipelineDB

logger = logging.getLogger(__name__)


def log_run_config(
    npc_key: str,
    stage: str,
    output_dir: str | Path,
    resolved_params: dict[str, Any],
    preflight_report: Optional[dict[str, Any]] = None,
    technique: Optional[str] = None,
    preset: Optional[str] = None,
) -> Path:
    """Write resolved parameters to run_config.yaml + run_config.json + DB snapshot.

    Args:
        npc_key: NPC identifier (e.g. "history_guide").
        stage: Pipeline stage name. One of:
            generate, sanitize, deepeval, train, export, evaluate, feedback.
        output_dir: Output directory for this run. Created if missing.
        resolved_params: ALL resolved parameter values (not just overrides).
            Every key from the parameter registry should be present with its
            final effective value.
        preflight_report: Optional preflight report dict from PreflightReport.
        technique: Optional technique name (template, docs, ollama, etc.).
        preset: Optional preset name (smoke, fast-3b, safe-any, etc.).

    Returns:
        Path to the written run_config.yaml file.

    Raises:
        OSError: If the output directory cannot be created or files written.
    """
    # ── Guard ──────────────────────────────────────────────────────────
    if not npc_key:
        raise ValueError("npc_key is required and must be non-empty")
    if not stage:
        raise ValueError("stage is required and must be non-empty")
    if not resolved_params:
        logger.warning("resolved_params is empty — audit trail will have no parameters")

    # ── Ensure output directory ────────────────────────────────────────
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Build record ───────────────────────────────────────────────────
    record: dict[str, Any] = {
        "stage": stage,
        "npc_key": npc_key,
        "technique": technique or "",
        "preset": preset or "",
        "timestamp": datetime.now().isoformat(),
        "parameters": resolved_params,
    }

    if preflight_report:
        record["preflight"] = preflight_report

    # ── Write YAML (human-readable) ────────────────────────────────────
    yaml_path = output_path / "run_config.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(record, f, default_flow_style=False, sort_keys=False, indent=2)

    # ── Write JSON (machine-parseable) ─────────────────────────────────
    json_path = output_path / "run_config.json"
    with open(json_path, "w") as f:
        json.dump(record, f, indent=2, default=str)

    # ── DB snapshot (best-effort) ──────────────────────────────────────
    _save_db_snapshot(
        npc_key=npc_key,
        resolved_params=resolved_params,
        preset=preset,
        technique=technique,
        file_path=str(yaml_path),
    )

    logger.info(
        "Run config written: YAML=%s JSON=%s",
        yaml_path,
        json_path,
    )
    return yaml_path


def _save_db_snapshot(
    npc_key: str,
    resolved_params: dict[str, Any],
    preset: Optional[str],
    technique: Optional[str],
    file_path: str,
) -> None:
    """Best-effort DB snapshot via PipelineDB.save_config_snapshot()."""
    try:
        db = PipelineDB()
        if db._mode == "none":
            logger.debug("PipelineDB not connected — skipping DB snapshot")
            return

        db.save_config_snapshot(
            npc_key=npc_key,
            full_config=resolved_params,
            preset=preset,
            technique=technique,
            file_path=file_path,
        )
        logger.debug("DB config snapshot saved for npc_key=%s", npc_key)
    except Exception as exc:
        logger.warning("Failed to save DB config snapshot: %s", exc)


def read_run_config(run_dir: str | Path) -> dict[str, Any]:
    """Read a run_config.yaml or run_config.json from a run directory.

    Tries YAML first (human-readable), falls back to JSON (machine-parseable).

    Args:
        run_dir: Path to a run output directory containing config files.

    Returns:
        Parsed config dict, or empty dict if neither file exists.

    Raises:
        yaml.YAMLError: If YAML exists but is malformed.
        json.JSONDecodeError: If JSON exists but is malformed (no YAML).
    """
    path = Path(run_dir)
    yaml_path = path / "run_config.yaml"
    json_path = path / "run_config.json"

    if yaml_path.exists():
        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}

    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)

    logger.warning("No run config found in %s", run_dir)
    return {}
