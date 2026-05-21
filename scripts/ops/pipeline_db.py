#!/usr/bin/env python3
"""
scripts/ops/pipeline_db.py — PostgreSQL/Supabase Pipeline DB Client

Provides a unified database client that pipeline scripts can use to emit
state to the PostgreSQL/Supabase pipeline tables. Supports two modes:

  1. Direct PostgreSQL (preferred): Uses psycopg2 for full CRUD via SQL.
  2. REST API fallback: Uses Supabase REST API via urllib (stdlib only)
     when direct DB access is unavailable.

Auto-detects the best available mode based on environment variables:

    SUPABASE_DB_URL        — PostgreSQL connection string for direct mode
    PIPELINE_DB_URL        — Optional override for the DB connection string
    SUPABASE_URL           — Base URL for REST API mode
    SUPABASE_KEY           — Anon/service key for REST API mode

When neither connection string is set, defaults to local Supabase params:

    host=127.0.0.1 port=15434 user=postgres password=postgres dbname=postgres

Usage:

    from scripts.ops.pipeline_db import PipelineDB

    with PipelineDB() as db:
        if db.ensure_connected():
            job = db.create_job(npc_key="history_guide", type="train",
                                command_id="train_001", command_args=[])
            db.update_job_status(job["id"], status="running")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urljoin

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

_DEFAULT_SUPABASE_HOST = "127.0.0.1"
_DEFAULT_SUPABASE_PORT = 15434
_DEFAULT_SUPABASE_USER = "postgres"
_DEFAULT_SUPABASE_PASS = "postgres"
_DEFAULT_SUPABASE_DB = "postgres"
_DEFAULT_REST_PORT = 16437

# REST API table endpoints (relative to SUPABASE_URL)
_TABLE_JOBS = "pipeline_jobs"
_TABLE_RUNS = "pipeline_runs"
_TABLE_ARTIFACTS = "pipeline_artifacts"
_TABLE_QUALITY_GATES = "dataset_quality_gates"
_TABLE_EVAL_SESSIONS = "eval_sessions"
_TABLE_CONFIG_SNAPSHOTS = "pipeline_config_snapshots"
_TABLE_API_KEYS = "api_keys"
_TABLE_AUDIT_LOG = "api_audit_log"


# ── Helpers ────────────────────────────────────────────────────────────────


def _iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _parse_db_url(url: str) -> dict[str, Any]:
    """Parse a PostgreSQL connection string into component parts.

    Handles formats like:
        postgresql://user:pass@host:port/dbname
        postgresql://user:pass@host/dbname
    """
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(url)
    return {
        "host": parsed.hostname or _DEFAULT_SUPABASE_HOST,
        "port": parsed.port or _DEFAULT_SUPABASE_PORT,
        "user": parsed.username or _DEFAULT_SUPABASE_USER,
        "password": parsed.password or _DEFAULT_SUPABASE_PASS,
        "dbname": parsed.path.lstrip("/") or _DEFAULT_SUPABASE_DB,
    }


def _build_default_conn_params() -> dict[str, Any]:
    """Return connection parameters from env vars or local Supabase defaults."""
    db_url = (
        os.environ.get("PIPELINE_DB_URL")
        or os.environ.get("SUPABASE_DB_URL")
    )
    if db_url:
        return _parse_db_url(db_url)

    return {
        "host": os.environ.get("PIPELINE_DB_HOST", _DEFAULT_SUPABASE_HOST),
        "port": int(os.environ.get("PIPELINE_DB_PORT", str(_DEFAULT_SUPABASE_PORT))),
        "user": os.environ.get("PIPELINE_DB_USER", _DEFAULT_SUPABASE_USER),
        "password": os.environ.get("PIPELINE_DB_PASS", _DEFAULT_SUPABASE_PASS),
        "dbname": os.environ.get("PIPELINE_DB_NAME", _DEFAULT_SUPABASE_DB),
    }


def _hash_api_key(key: str) -> str:
    """Return a SHA-256 hex digest of the given API key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _sanitize_kwargs(**kwargs: Any) -> dict[str, Any]:
    """Remove keys with None values from the dict for DB insertion."""
    return {k: v for k, v in kwargs.items() if v is not None}


# ── PipelineDB ─────────────────────────────────────────────────────────────


class PipelineDB:
    """Unified database client for pipeline state management.

    Auto-detects direct PostgreSQL vs REST API mode and provides a common
    API surface for CRUD operations on pipeline tables.

    All methods are best-effort: they return sensible defaults (None, False,
    empty list) on failure rather than raising, except for ImportError when
    psycopg2 is missing and direct mode is required.
    """

    def __init__(
        self,
        db_url: Optional[str] = None,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ) -> None:
        self._conn: Any = None
        self._mode: Optional[str] = None  # "direct" or "rest"
        self._supabase_url: Optional[str] = None
        self._supabase_key: Optional[str] = None

        # Resolve DB connection — explicit arg wins over env var
        resolved_db_url = db_url or os.environ.get("PIPELINE_DB_URL") or os.environ.get("SUPABASE_DB_URL")
        resolved_supabase_url = supabase_url or os.environ.get("SUPABASE_URL")
        resolved_supabase_key = supabase_key or os.environ.get("SUPABASE_KEY")

        if resolved_db_url:
            # Direct mode with explicit connection string
            self._conn_params = _parse_db_url(resolved_db_url)
            self._mode = "direct"
        else:
            # Try direct with defaults; fall back to REST
            self._conn_params = _build_default_conn_params()

        if resolved_supabase_url:
            self._supabase_url = resolved_supabase_url.rstrip("/")
        else:
            self._supabase_url = f"http://{_DEFAULT_SUPABASE_HOST}:{_DEFAULT_REST_PORT}"

        self._supabase_key = resolved_supabase_key or ""
        self._last_status: Optional[int] = None

    @property
    def connected(self) -> bool:
        """Return True if a connection mode has been established.

        Once ensure_connected() successfully probes the database, _mode is
        set to \"direct\" or \"rest\". This property reflects that state
        without performing additional I/O.
        """
        return self._mode is not None

    # ── Column name allowlist ──────────────────────────────────────────
    # Only these column names may be used as dynamic SQL identifiers from
    # **kwargs. Any key not in this set is skipped with a warning.
    SANITIZE_ALLOWLIST: set[str] = {
        "status", "progress", "error", "wandb_url", "logs", "name",
        "role", "is_active", "key_prefix", "version", "config",
        "spec_path", "run_id", "technique", "preset", "base_model",
        "npc_key", "category", "score", "pass_rate", "total", "passed",
        "failed", "failure_reason", "recommendation", "stage", "model",
        "model_id", "duration_s", "step", "tool", "output_dir",
        "command_id", "command_args",
        "pid", "recoveredAt", "retryCount", "retryMax", "retryDelayBaseMs",
        "nextRetryAt", "cwd", "artifact_type", "file_path", "file_size_bytes",
        "metadata", "dataset_path", "judge_model", "candidate_path",
        "baseline_path", "full_config", "run_dir",
    }

    @staticmethod
    def _filter_extra(extra: dict[str, Any]) -> dict[str, Any]:
        """Filter a kwargs dict to only allow known-safe column names.

        Unknown keys are skipped with a warning to prevent SQL injection
        via dynamic column names.
        """
        filtered: dict[str, Any] = {}
        for key, val in extra.items():
            if key in PipelineDB.SANITIZE_ALLOWLIST:
                filtered[key] = val
            else:
                logger.warning("Skipping unknown column '%s' (not in allowlist)", key)
        return filtered

    # ── Connection management ──────────────────────────────────────────

    def ensure_connected(self) -> bool:
        """Test and return connection status.

        Returns True if a working connection is established, False otherwise.
        """
        if self._mode == "direct":
            return self._ensure_direct()
        elif self._mode == "rest":
            return self._ensure_rest()
        else:
            return self._auto_detect()

    def _auto_detect(self) -> bool:
        """Try direct mode first; fall back to REST API mode."""
        if self._ensure_direct():
            self._mode = "direct"
            return True
        logger.info("Direct PostgreSQL connection failed; falling back to REST API mode")
        if self._ensure_rest():
            self._mode = "rest"
            return True
        logger.warning("Both direct and REST API connections failed")
        return False

    def _ensure_direct(self) -> bool:
        """Attempt to establish or verify a direct psycopg2 connection."""
        if self._conn is not None:
            try:
                cur = self._conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                return True
            except Exception:
                self._conn = None

        try:
            import psycopg2  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "psycopg2 is not installed. Install it with: "
                "pip install psycopg2-binary"
            )
            return False

        try:
            self._conn = psycopg2.connect(**self._conn_params)
            self._conn.autocommit = True
            return True
        except Exception as exc:
            logger.warning("Failed to connect to PostgreSQL: %s", exc)
            self._conn = None
            return False

    def _ensure_rest(self) -> bool:
        """Check REST API availability with a lightweight request."""
        if not self._supabase_url:
            return False
        try:
            from urllib.request import Request, urlopen

            url = urljoin(self._supabase_url + "/", "rest/v1/")
            req = Request(url, method="HEAD")
            if self._supabase_key:
                req.add_header("apikey", self._supabase_key)
                req.add_header("Authorization", f"Bearer {self._supabase_key}")
            # Short timeout — the HEAD probe should be fast
            import socket

            timeout = socket.getdefaulttimeout()
            urlopen(req, timeout=5)
            return True
        except Exception:
            return False

    def _ensure_direct_connected(self) -> None:
        """Ensure direct connection is alive; reconnect if needed.

        Raises ImportError with installation instructions if psycopg2
        is not installed, or RuntimeError if the connection fails.
        """
        if self._mode != "direct":
            return
        try:
            import psycopg2  # type: ignore[import-untyped]  # noqa: F401
        except ImportError:
            raise ImportError(
                "psycopg2 is required for direct PostgreSQL mode. "
                "Install it with: pip install psycopg2-binary"
            )
        if not self._ensure_direct():
            raise RuntimeError("Direct PostgreSQL connection is not available")

    # ── Row helpers ────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(cursor: Any) -> list[dict[str, Any]]:
        """Convert psycopg2 cursor results to a list of dicts.

        Uses cursor.description to extract column names.
        Returns an empty list if there are no results.
        """
        if cursor.description is None:
            return []
        columns = [col[0] for col in cursor.description]
        rows: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, row)))
        return rows

    # ── REST helpers ───────────────────────────────────────────────────

    def _rest_request(
        self,
        method: str,
        table: str,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Make a REST API request to Supabase.

        Returns the parsed JSON response on success, or None on failure.
        For INSERT operations that return a row, this returns the created row.
        """
        if self._mode != "rest":
            return None

        from urllib.request import Request, urlopen

        url = urljoin(self._supabase_url + "/", f"rest/v1/{table}")
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._supabase_key:
            headers["apikey"] = self._supabase_key
            headers["Authorization"] = f"Bearer {self._supabase_key}"

        # Auto-add Prefer header for mutations to get the created row back
        if method in ("POST", "PATCH"):
            headers["Prefer"] = "return=representation"

        if params:
            query_string = urlencode(params, doseq=True)
            url = f"{url}?{query_string}"

        body: Optional[bytes] = None
        if data is not None:
            body = json.dumps(data, default=str).encode("utf-8")

        try:
            req = Request(url, data=body, headers=headers, method=method)
            with urlopen(req, timeout=30) as resp:
                self._last_status = resp.status
                raw = resp.read().decode("utf-8")
                if raw.strip():
                    return json.loads(raw)
                return None
        except Exception as exc:
            self._last_status = getattr(exc, "code", None)  # HTTPError has .code
            logger.warning("REST %s %s failed: %s", method, table, exc)
            return None

    # ── Job operations ─────────────────────────────────────────────────

    def create_job(
        self,
        npc_key: str,
        type: str,
        command_id: str,
        command_args: list,
        **kwargs: Any,
    ) -> dict:
        """Insert a new pipeline_jobs row and return it as a dict.

        Args:
            npc_key: NPC identifier.
            type: Job type (e.g. "train", "generate", "evaluate").
            command_id: Unique command identifier.
            command_args: List of command arguments.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            The created row as a dict, or an empty dict on failure.
        """
        job_id = str(uuid.uuid4())
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_create_job(job_id, npc_key, type, command_id, command_args, now, extra)
        elif self._mode == "rest":
            return self._rest_create_job(job_id, npc_key, type, command_id, command_args, now, extra)

        logger.warning("PipelineDB is not connected; cannot create job")
        return {}

    def _direct_create_job(
        self,
        job_id: str,
        npc_key: str,
        type: str,
        command_id: str,
        command_args: list,
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO pipeline_jobs (id, npc_key, type, command_id, command_args, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (job_id, npc_key, type, command_id, json.dumps(command_args), "pending", now, now),
            )
            row = self._row_to_dict(cur)
            cur.close()
            if row:
                logger.info("Created job %s for NPC %s (type=%s)", job_id, npc_key, type)
                return row[0]
            return {}
        except Exception as exc:
            logger.warning("Failed to create job for NPC %s: %s", npc_key, exc)
            return {}

    def _rest_create_job(
        self,
        job_id: str,
        npc_key: str,
        type: str,
        command_id: str,
        command_args: list,
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        payload: dict[str, Any] = {
            "id": job_id,
            "npc_key": npc_key,
            "type": type,
            "command_id": command_id,
            "command_args": command_args,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_JOBS, data=payload)
        if result:
            logger.info("REST: Created job %s for NPC %s", job_id, npc_key)
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        return {}

    def update_job_status(
        self,
        job_id: str,
        status: str,
        exit_code: Optional[int] = None,
        error: Optional[str] = None,
        progress: Optional[int] = None,
        loss: Optional[float] = None,
        wandb_url: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Update a job's status and optional metrics.

        Args:
            job_id: UUID of the job to update.
            status: New status value (e.g. "running", "completed", "failed").
            exit_code: Optional process exit code.
            error: Optional error message.
            progress: Optional progress percentage (0-100).
            loss: Optional training loss value.
            wandb_url: Optional W&B run URL.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            True if the update succeeded, False otherwise.
        """
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_update_job(job_id, status, exit_code, error, progress, loss, wandb_url, now, extra)
        elif self._mode == "rest":
            return self._rest_update_job(job_id, status, exit_code, error, progress, loss, wandb_url, now, extra)

        logger.warning("PipelineDB is not connected; cannot update job %s", job_id)
        return False

    def _direct_update_job(
        self,
        job_id: str,
        status: str,
        exit_code: Optional[int],
        error: Optional[str],
        progress: Optional[int],
        loss: Optional[float],
        wandb_url: Optional[str],
        now: str,
        extra: dict[str, Any],
    ) -> bool:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            fields: list[str] = [
                "status = %s",
                "updated_at = %s",
            ]
            values: list[Any] = [status, now]

            if exit_code is not None:
                fields.append("exit_code = %s")
                values.append(exit_code)
            if error is not None:
                fields.append("error = %s")
                values.append(error)
            if progress is not None:
                fields.append("progress = %s")
                values.append(progress)
            if loss is not None:
                fields.append("loss = %s")
                values.append(loss)
            if wandb_url is not None:
                fields.append("wandb_url = %s")
                values.append(wandb_url)

            # Add any extra kwargs as allowlisted dynamic fields
            for key, val in self._filter_extra(extra).items():
                fields.append(f"{key} = %s")
                values.append(val)

            values.append(job_id)
            query = f"UPDATE pipeline_jobs SET {', '.join(fields)} WHERE id = %s"
            cur.execute(query, values)
            cur.close()
            logger.info("Updated job %s status to %s", job_id, status)
            return True
        except Exception as exc:
            logger.warning("Failed to update job %s: %s", job_id, exc)
            return False

    def _rest_update_job(
        self,
        job_id: str,
        status: str,
        exit_code: Optional[int],
        error: Optional[str],
        progress: Optional[int],
        loss: Optional[float],
        wandb_url: Optional[str],
        now: str,
        extra: dict[str, Any],
    ) -> bool:
        payload: dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if exit_code is not None:
            payload["exit_code"] = exit_code
        if error is not None:
            payload["error"] = error
        if progress is not None:
            payload["progress"] = progress
        if loss is not None:
            payload["loss"] = loss
        if wandb_url is not None:
            payload["wandb_url"] = wandb_url
        payload.update(extra)

        params = {"id": f"eq.{job_id}"}
        result = self._rest_request("PATCH", _TABLE_JOBS, params=params, data=payload)
        if result is not None or self._rest_probe_success("PATCH", _TABLE_JOBS):
            logger.info("REST: Updated job %s status to %s", job_id, status)
            return True
        return False

    def _rest_probe_success(self, method: str, table: str) -> bool:
        """Check whether the last REST request likely succeeded.

        REST PATCH returns 204 No Content (empty response), so a None result
        with no exception means success. This method checks the stored HTTP
        status against success codes (200, 201, 204).
        """
        if self._last_status is None:
            return False
        return self._last_status in (200, 201, 204)

    def get_job(self, job_id: str) -> Optional[dict]:
        """Fetch a single job by UUID.

        Returns the job row as a dict, or None if not found.
        """
        if self._mode == "direct":
            return self._direct_get_job(job_id)
        elif self._mode == "rest":
            return self._rest_get_job(job_id)

        logger.warning("PipelineDB is not connected; cannot get job %s", job_id)
        return None

    def _direct_get_job(self, job_id: str) -> Optional[dict]:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM pipeline_jobs WHERE id = %s", (job_id,))
            rows = self._row_to_dict(cur)
            cur.close()
            return rows[0] if rows else None
        except Exception as exc:
            logger.warning("Failed to get job %s: %s", job_id, exc)
            return None

    def _rest_get_job(self, job_id: str) -> Optional[dict]:
        params = {"id": f"eq.{job_id}", "limit": 1}
        result = self._rest_request("GET", _TABLE_JOBS, params=params)
        if isinstance(result, list) and result:
            return result[0]
        return None

    def list_jobs(
        self,
        npc_key: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[dict]:
        """List jobs with optional filters.

        Args:
            npc_key: Optional NPC key filter.
            status: Optional status filter (e.g. "running", "completed").
            limit: Maximum number of jobs to return (default 50).
            **kwargs: Additional filter columns for forward compatibility.

        Returns:
            A list of job row dicts, newest first.
        """
        if self._mode == "direct":
            return self._direct_list_jobs(npc_key, status, limit)
        elif self._mode == "rest":
            return self._rest_list_jobs(npc_key, status, limit)

        logger.warning("PipelineDB is not connected; cannot list jobs")
        return []

    def _direct_list_jobs(self, npc_key: Optional[str], status: Optional[str], limit: int) -> list[dict]:
        try:
            self._ensure_direct_connected()
            conditions: list[str] = []
            values: list[Any] = []

            if npc_key is not None:
                conditions.append("npc_key = %s")
                values.append(npc_key)
            if status is not None:
                conditions.append("status = %s")
                values.append(status)

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            cur = self._conn.cursor()
            query = f"SELECT * FROM pipeline_jobs {where_clause} ORDER BY created_at DESC LIMIT %s"
            values.append(limit)
            cur.execute(query, values)
            rows = self._row_to_dict(cur)
            cur.close()
            return rows
        except Exception as exc:
            logger.warning("Failed to list jobs: %s", exc)
            return []

    def _rest_list_jobs(self, npc_key: Optional[str], status: Optional[str], limit: int) -> list[dict]:
        params: dict[str, Any] = {"order": "created_at.desc", "limit": limit}
        if npc_key is not None:
            params["npc_key"] = f"eq.{npc_key}"
        if status is not None:
            params["status"] = f"eq.{status}"
        result = self._rest_request("GET", _TABLE_JOBS, params=params)
        if isinstance(result, list):
            return result
        return []

    # ── Run operations ─────────────────────────────────────────────────

    def create_run(
        self,
        npc_key: str,
        run_id: str,
        run_dir: str,
        **kwargs: Any,
    ) -> dict:
        """Insert a pipeline_runs row and return it as a dict.

        Args:
            npc_key: NPC identifier.
            run_id: Unique run identifier.
            run_dir: Path to the run directory.
            **kwargs: Additional columns (stage, technique, preset, spec_path,
                      model, base_model, status, metrics, etc.).

        Returns:
            The created row as a dict, or an empty dict on failure.
        """
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_create_run(npc_key, run_id, run_dir, now, extra)
        elif self._mode == "rest":
            return self._rest_create_run(npc_key, run_id, run_dir, now, extra)

        logger.warning("PipelineDB is not connected; cannot create run")
        return {}

    def _direct_create_run(
        self,
        npc_key: str,
        run_id: str,
        run_dir: str,
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()

            columns = ["npc_key", "run_id", "run_dir", "created_at", "updated_at"]
            placeholders = ["%s", "%s", "%s", "%s", "%s"]
            values: list[Any] = [npc_key, run_id, run_dir, now, now]

            for key, val in self._filter_extra(extra).items():
                columns.append(key)
                placeholders.append("%s")
                values.append(val)

            query = (
                f"INSERT INTO pipeline_runs ({', '.join(columns)}) "
                f"VALUES ({', '.join(placeholders)}) "
                f"RETURNING *"
            )
            cur.execute(query, values)
            rows = self._row_to_dict(cur)
            cur.close()
            if rows:
                logger.info("Created run %s for NPC %s", run_id, npc_key)
                return rows[0]
            return {}
        except Exception as exc:
            logger.warning("Failed to create run for NPC %s: %s", npc_key, exc)
            return {}

    def _rest_create_run(
        self,
        npc_key: str,
        run_id: str,
        run_dir: str,
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        payload: dict[str, Any] = {
            "npc_key": npc_key,
            "run_id": run_id,
            "run_dir": run_dir,
            "created_at": now,
            "updated_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_RUNS, data=payload)
        if result:
            logger.info("REST: Created run %s for NPC %s", run_id, npc_key)
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        return {}

    def update_run_metrics(
        self,
        npc_key: str,
        run_id: str,
        metrics: dict[str, Any],
        **kwargs: Any,
    ) -> bool:
        """Update the metrics JSONB column for a run.

        Args:
            npc_key: NPC identifier.
            run_id: Unique run identifier.
            metrics: Dict of metric key-value pairs to store as JSONB.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            True if the update succeeded, False otherwise.
        """
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_update_run_metrics(npc_key, run_id, metrics, now, extra)
        elif self._mode == "rest":
            return self._rest_update_run_metrics(npc_key, run_id, metrics, now, extra)

        logger.warning("PipelineDB is not connected; cannot update run metrics")
        return False

    def _direct_update_run_metrics(
        self,
        npc_key: str,
        run_id: str,
        metrics: dict[str, Any],
        now: str,
        extra: dict[str, Any],
    ) -> bool:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            fields: list[str] = ["metrics = %s", "updated_at = %s"]
            values: list[Any] = [json.dumps(metrics), now]

            for key, val in self._filter_extra(extra).items():
                fields.append(f"{key} = %s")
                values.append(val)

            values.extend([npc_key, run_id])
            cur.execute(
                f"UPDATE pipeline_runs SET {', '.join(fields)} "
                "WHERE npc_key = %s AND run_id = %s",
                values,
            )
            cur.close()
            logger.info("Updated metrics for run %s (NPC %s)", run_id, npc_key)
            return True
        except Exception as exc:
            logger.warning("Failed to update run metrics for %s/%s: %s", npc_key, run_id, exc)
            return False

    def _rest_update_run_metrics(
        self,
        npc_key: str,
        run_id: str,
        metrics: dict[str, Any],
        now: str,
        extra: dict[str, Any],
    ) -> bool:
        payload: dict[str, Any] = {
            "metrics": metrics,
            "updated_at": now,
        }
        payload.update(extra)
        params = {
            "npc_key": f"eq.{npc_key}",
            "run_id": f"eq.{run_id}",
        }
        result = self._rest_request("PATCH", _TABLE_RUNS, params=params, data=payload)
        if result is not None:
            logger.info("REST: Updated metrics for run %s (NPC %s)", run_id, npc_key)
            return True
        return False

    def get_run(self, npc_key: str, run_id: str) -> Optional[dict]:
        """Fetch a single run by NPC key and run ID.

        Returns the run row as a dict, or None if not found.
        """
        if self._mode == "direct":
            return self._direct_get_run(npc_key, run_id)
        elif self._mode == "rest":
            return self._rest_get_run(npc_key, run_id)

        logger.warning("PipelineDB is not connected; cannot get run")
        return None

    def _direct_get_run(self, npc_key: str, run_id: str) -> Optional[dict]:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM pipeline_runs WHERE npc_key = %s AND run_id = %s",
                (npc_key, run_id),
            )
            rows = self._row_to_dict(cur)
            cur.close()
            return rows[0] if rows else None
        except Exception as exc:
            logger.warning("Failed to get run %s/%s: %s", npc_key, run_id, exc)
            return None

    def _rest_get_run(self, npc_key: str, run_id: str) -> Optional[dict]:
        params = {
            "npc_key": f"eq.{npc_key}",
            "run_id": f"eq.{run_id}",
            "limit": 1,
        }
        result = self._rest_request("GET", _TABLE_RUNS, params=params)
        if isinstance(result, list) and result:
            return result[0]
        return None

    def list_runs(
        self,
        npc_key: Optional[str] = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> list[dict]:
        """List runs, newest first, with optional NPC key filter.

        Args:
            npc_key: Optional NPC key filter.
            limit: Maximum number of runs to return (default 50).
            **kwargs: Additional filter columns for forward compatibility.

        Returns:
            A list of run row dicts.
        """
        if self._mode == "direct":
            return self._direct_list_runs(npc_key, limit)
        elif self._mode == "rest":
            return self._rest_list_runs(npc_key, limit)

        logger.warning("PipelineDB is not connected; cannot list runs")
        return []

    def _direct_list_runs(self, npc_key: Optional[str], limit: int) -> list[dict]:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            if npc_key:
                cur.execute(
                    "SELECT * FROM pipeline_runs WHERE npc_key = %s ORDER BY created_at DESC LIMIT %s",
                    (npc_key, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
            rows = self._row_to_dict(cur)
            cur.close()
            return rows
        except Exception as exc:
            logger.warning("Failed to list runs: %s", exc)
            return []

    def _rest_list_runs(self, npc_key: Optional[str], limit: int) -> list[dict]:
        params: dict[str, Any] = {"order": "created_at.desc", "limit": limit}
        if npc_key is not None:
            params["npc_key"] = f"eq.{npc_key}"
        result = self._rest_request("GET", _TABLE_RUNS, params=params)
        if isinstance(result, list):
            return result
        return []

    # ── Artifact operations ────────────────────────────────────────────

    def create_artifact(
        self,
        npc_key: str,
        artifact_type: str,
        file_path: str,
        run_id: Optional[str] = None,
        technique: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> dict:
        """Insert a pipeline_artifacts row and return it as a dict.

        Args:
            npc_key: NPC identifier.
            artifact_type: Type of artifact (e.g. "gguf", "dataset", "checkpoint").
            file_path: Path to the artifact file.
            run_id: Optional associated run ID.
            technique: Optional generation/training technique.
            file_size_bytes: Optional file size in bytes.
            metadata: Optional metadata dict to store as JSONB.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            The created row as a dict, or an empty dict on failure.
        """
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_create_artifact(
                npc_key, artifact_type, file_path, run_id, technique,
                file_size_bytes, metadata, now, extra,
            )
        elif self._mode == "rest":
            return self._rest_create_artifact(
                npc_key, artifact_type, file_path, run_id, technique,
                file_size_bytes, metadata, now, extra,
            )

        logger.warning("PipelineDB is not connected; cannot create artifact")
        return {}

    def _direct_create_artifact(
        self,
        npc_key: str,
        artifact_type: str,
        file_path: str,
        run_id: Optional[str],
        technique: Optional[str],
        file_size_bytes: Optional[int],
        metadata: Optional[dict[str, Any]],
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO pipeline_artifacts
                    (npc_key, artifact_type, file_path, run_id, technique,
                     file_size_bytes, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    npc_key,
                    artifact_type,
                    file_path,
                    run_id,
                    technique,
                    file_size_bytes,
                    json.dumps(metadata) if metadata else None,
                    now,
                ),
            )
            rows = self._row_to_dict(cur)
            cur.close()
            if rows:
                logger.info("Created artifact %s for NPC %s", artifact_type, npc_key)
                return rows[0]
            return {}
        except Exception as exc:
            logger.warning("Failed to create artifact for NPC %s: %s", npc_key, exc)
            return {}

    def _rest_create_artifact(
        self,
        npc_key: str,
        artifact_type: str,
        file_path: str,
        run_id: Optional[str],
        technique: Optional[str],
        file_size_bytes: Optional[int],
        metadata: Optional[dict[str, Any]],
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        payload: dict[str, Any] = {
            "npc_key": npc_key,
            "artifact_type": artifact_type,
            "file_path": file_path,
            "run_id": run_id,
            "technique": technique,
            "file_size_bytes": file_size_bytes,
            "metadata": metadata,
            "created_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_ARTIFACTS, data=payload)
        if result:
            logger.info("REST: Created artifact %s for NPC %s", artifact_type, npc_key)
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        return {}

    def list_artifacts(
        self,
        npc_key: Optional[str] = None,
        artifact_type: Optional[str] = None,
        **kwargs: Any,
    ) -> list[dict]:
        """List artifacts with optional filters.

        Args:
            npc_key: Optional NPC key filter.
            artifact_type: Optional type filter (e.g. "gguf", "dataset").
            **kwargs: Additional filter columns for forward compatibility.

        Returns:
            A list of artifact row dicts, newest first.
        """
        if self._mode == "direct":
            return self._direct_list_artifacts(npc_key, artifact_type)
        elif self._mode == "rest":
            return self._rest_list_artifacts(npc_key, artifact_type)

        logger.warning("PipelineDB is not connected; cannot list artifacts")
        return []

    def _direct_list_artifacts(
        self,
        npc_key: Optional[str],
        artifact_type: Optional[str],
    ) -> list[dict]:
        try:
            self._ensure_direct_connected()
            conditions: list[str] = []
            values: list[Any] = []

            if npc_key is not None:
                conditions.append("npc_key = %s")
                values.append(npc_key)
            if artifact_type is not None:
                conditions.append("artifact_type = %s")
                values.append(artifact_type)

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            cur = self._conn.cursor()
            cur.execute(
                f"SELECT * FROM pipeline_artifacts {where_clause} ORDER BY created_at DESC",
                values,
            )
            rows = self._row_to_dict(cur)
            cur.close()
            return rows
        except Exception as exc:
            logger.warning("Failed to list artifacts: %s", exc)
            return []

    def _rest_list_artifacts(
        self,
        npc_key: Optional[str],
        artifact_type: Optional[str],
    ) -> list[dict]:
        params: dict[str, Any] = {"order": "created_at.desc"}
        if npc_key is not None:
            params["npc_key"] = f"eq.{npc_key}"
        if artifact_type is not None:
            params["artifact_type"] = f"eq.{artifact_type}"
        result = self._rest_request("GET", _TABLE_ARTIFACTS, params=params)
        if isinstance(result, list):
            return result
        return []

    # ── Quality gate operations ────────────────────────────────────────

    def create_quality_gate(
        self,
        npc_key: str,
        technique: str,
        total_samples: int,
        passed: int,
        failed: int,
        pass_rate: float,
        metrics: Optional[dict[str, Any]] = None,
        categories: Optional[dict[str, Any]] = None,
        failures: Optional[list[dict[str, Any]]] = None,
        judge_model: str = "qwen3:latest",
        dataset_path: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        """Insert a dataset_quality_gates row and return it as a dict.

        Args:
            npc_key: NPC identifier.
            technique: Generation technique used.
            total_samples: Total number of samples evaluated.
            passed: Number of samples that passed.
            failed: Number of samples that failed.
            pass_rate: Pass rate as a float (0.0 to 1.0).
            metrics: Optional metrics dict (JSONB).
            categories: Optional per-category breakdown dict (JSONB).
            failures: Optional list of failure dicts (JSONB).
            judge_model: Judge model name (default "qwen3:latest").
            dataset_path: Optional path to the evaluated dataset.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            The created row as a dict, or an empty dict on failure.
        """
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        eval_id = str(uuid.uuid4())

        if self._mode == "direct":
            return self._direct_create_quality_gate(
                eval_id, npc_key, technique, total_samples, passed, failed,
                pass_rate, metrics, categories, failures, judge_model,
                dataset_path, now, extra,
            )
        elif self._mode == "rest":
            return self._rest_create_quality_gate(
                eval_id, npc_key, technique, total_samples, passed, failed,
                pass_rate, metrics, categories, failures, judge_model,
                dataset_path, now, extra,
            )

        logger.warning("PipelineDB is not connected; cannot create quality gate")
        return {}

    def _direct_create_quality_gate(
        self,
        eval_id: str,
        npc_key: str,
        technique: str,
        total_samples: int,
        passed: int,
        failed: int,
        pass_rate: float,
        metrics: Optional[dict[str, Any]],
        categories: Optional[dict[str, Any]],
        failures: Optional[list[dict[str, Any]]],
        judge_model: str,
        dataset_path: Optional[str],
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO dataset_quality_gates
                    (id, npc_key, technique, total_samples, passed, failed,
                     pass_rate, metrics, categories, failures, judge_model,
                     dataset_path, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    eval_id,
                    npc_key,
                    technique,
                    total_samples,
                    passed,
                    failed,
                    pass_rate,
                    json.dumps(metrics) if metrics else None,
                    json.dumps(categories) if categories else None,
                    json.dumps(failures) if failures else None,
                    judge_model,
                    dataset_path,
                    now,
                ),
            )
            rows = self._row_to_dict(cur)
            cur.close()
            if rows:
                logger.info(
                    "Created quality gate for NPC %s (pass_rate=%.2f)",
                    npc_key, pass_rate,
                )
                return rows[0]
            return {}
        except Exception as exc:
            logger.warning("Failed to create quality gate for NPC %s: %s", npc_key, exc)
            return {}

    def _rest_create_quality_gate(
        self,
        eval_id: str,
        npc_key: str,
        technique: str,
        total_samples: int,
        passed: int,
        failed: int,
        pass_rate: float,
        metrics: Optional[dict[str, Any]],
        categories: Optional[dict[str, Any]],
        failures: Optional[list[dict[str, Any]]],
        judge_model: str,
        dataset_path: Optional[str],
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        payload: dict[str, Any] = {
            "id": eval_id,
            "npc_key": npc_key,
            "technique": technique,
            "total_samples": total_samples,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "metrics": metrics,
            "categories": categories,
            "failures": failures,
            "judge_model": judge_model,
            "dataset_path": dataset_path,
            "created_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_QUALITY_GATES, data=payload)
        if result:
            logger.info(
                "REST: Created quality gate for NPC %s (pass_rate=%.2f)",
                npc_key, pass_rate,
            )
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        return {}

    # ── Eval session operations ────────────────────────────────────────

    def create_eval_session(
        self,
        npc_key: str,
        **kwargs: Any,
    ) -> dict:
        """Insert an eval_sessions row and return it as a dict.

        Args:
            npc_key: NPC identifier.
            **kwargs: All other columns (candidate_path, baseline_path,
                      judge_model, status, metrics, etc.).

        Returns:
            The created row as a dict, or an empty dict on failure.
        """
        session_id = str(uuid.uuid4())
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_create_eval_session(session_id, npc_key, now, extra)
        elif self._mode == "rest":
            return self._rest_create_eval_session(session_id, npc_key, now, extra)

        logger.warning("PipelineDB is not connected; cannot create eval session")
        return {}

    def _direct_create_eval_session(
        self,
        session_id: str,
        npc_key: str,
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()

            columns = ["id", "npc_key", "created_at"]
            placeholders = ["%s", "%s", "%s"]
            values: list[Any] = [session_id, npc_key, now]

            for key, val in self._filter_extra(extra).items():
                columns.append(key)
                placeholders.append("%s")
                values.append(val)

            query = (
                f"INSERT INTO eval_sessions ({', '.join(columns)}) "
                f"VALUES ({', '.join(placeholders)}) RETURNING *"
            )
            cur.execute(query, values)
            rows = self._row_to_dict(cur)
            cur.close()
            if rows:
                logger.info("Created eval session %s for NPC %s", session_id, npc_key)
                return rows[0]
            return {}
        except Exception as exc:
            logger.warning("Failed to create eval session for NPC %s: %s", npc_key, exc)
            return {}

    def _rest_create_eval_session(
        self,
        session_id: str,
        npc_key: str,
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        payload: dict[str, Any] = {
            "id": session_id,
            "npc_key": npc_key,
            "created_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_EVAL_SESSIONS, data=payload)
        if result:
            logger.info("REST: Created eval session %s for NPC %s", session_id, npc_key)
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        return {}

    # ── Config snapshot operations ─────────────────────────────────────

    def save_config_snapshot(
        self,
        npc_key: str,
        full_config: dict[str, Any],
        preset: Optional[str] = None,
        technique: Optional[str] = None,
        file_path: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        """Insert a pipeline_config_snapshots row and return it as a dict.

        Args:
            npc_key: NPC identifier.
            full_config: Full training/generation config dict (stored as JSONB).
            preset: Optional preset name.
            technique: Optional technique name.
            file_path: Optional path to the config file on disk.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            The created row as a dict, or an empty dict on failure.
        """
        snapshot_id = str(uuid.uuid4())
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_save_config_snapshot(
                snapshot_id, npc_key, full_config, preset, technique,
                file_path, now, extra,
            )
        elif self._mode == "rest":
            return self._rest_save_config_snapshot(
                snapshot_id, npc_key, full_config, preset, technique,
                file_path, now, extra,
            )

        logger.warning("PipelineDB is not connected; cannot save config snapshot")
        return {}

    def _direct_save_config_snapshot(
        self,
        snapshot_id: str,
        npc_key: str,
        full_config: dict[str, Any],
        preset: Optional[str],
        technique: Optional[str],
        file_path: Optional[str],
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO pipeline_config_snapshots
                    (id, npc_key, full_config, preset, technique, file_path, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    snapshot_id,
                    npc_key,
                    json.dumps(full_config),
                    preset,
                    technique,
                    file_path,
                    now,
                ),
            )
            rows = self._row_to_dict(cur)
            cur.close()
            if rows:
                logger.info("Saved config snapshot %s for NPC %s", snapshot_id, npc_key)
                return rows[0]
            return {}
        except Exception as exc:
            logger.warning("Failed to save config snapshot for NPC %s: %s", npc_key, exc)
            return {}

    def _rest_save_config_snapshot(
        self,
        snapshot_id: str,
        npc_key: str,
        full_config: dict[str, Any],
        preset: Optional[str],
        technique: Optional[str],
        file_path: Optional[str],
        now: str,
        extra: dict[str, Any],
    ) -> dict:
        payload: dict[str, Any] = {
            "id": snapshot_id,
            "npc_key": npc_key,
            "full_config": full_config,
            "preset": preset,
            "technique": technique,
            "file_path": file_path,
            "created_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_CONFIG_SNAPSHOTS, data=payload)
        if result:
            logger.info(
                "REST: Saved config snapshot %s for NPC %s", snapshot_id, npc_key,
            )
            if isinstance(result, list):
                return result[0] if result else {}
            return result
        return {}

    # ── API key operations ────────────────────────────────────────────

    def validate_api_key(self, api_key: str) -> Optional[dict]:
        """Hash the key and look it up in the api_keys table.

        Args:
            api_key: The raw API key to validate.

        Returns:
            The key info dict if valid, or None if not found/error.
        """
        key_hash = _hash_api_key(api_key)

        if self._mode == "direct":
            return self._direct_validate_api_key(key_hash)
        elif self._mode == "rest":
            return self._rest_validate_api_key(key_hash)

        logger.warning("PipelineDB is not connected; cannot validate API key")
        return None

    def _direct_validate_api_key(self, key_hash: str) -> Optional[dict]:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM api_keys WHERE key_hash = %s AND is_active = true",
                (key_hash,),
            )
            rows = self._row_to_dict(cur)
            cur.close()
            if rows:
                return rows[0]
            return None
        except Exception as exc:
            logger.warning("Failed to validate API key: %s", exc)
            return None

    def _rest_validate_api_key(self, key_hash: str) -> Optional[dict]:
        params = {
            "key_hash": f"eq.{key_hash}",
            "is_active": "eq.true",
            "limit": 1,
        }
        result = self._rest_request("GET", _TABLE_API_KEYS, params=params)
        if isinstance(result, list) and result:
            return result[0]
        return None

    # ── Audit operations ───────────────────────────────────────────────

    def log_audit_event(
        self,
        api_key_id: Optional[str] = None,
        user_role: Optional[str] = None,
        method: str = "",
        path: str = "",
        status_code: Optional[int] = None,
        request_body: Optional[str] = None,
        ip_address: Optional[str] = None,
        duration_ms: Optional[int] = None,
        **kwargs: Any,
    ) -> bool:
        """Insert an api_audit_log row.

        Args:
            api_key_id: Optional API key ID that made the request.
            user_role: Optional user role.
            method: HTTP method.
            path: Request path.
            status_code: Optional HTTP status code.
            request_body: Optional request body string.
            ip_address: Optional requester IP address.
            duration_ms: Optional request duration in milliseconds.
            **kwargs: Additional columns for forward compatibility.

        Returns:
            True if the insert succeeded, False otherwise.
        """
        now = _iso_now()
        extra = _sanitize_kwargs(**kwargs)

        if self._mode == "direct":
            return self._direct_log_audit_event(
                api_key_id, user_role, method, path, status_code,
                request_body, ip_address, duration_ms, now, extra,
            )
        elif self._mode == "rest":
            return self._rest_log_audit_event(
                api_key_id, user_role, method, path, status_code,
                request_body, ip_address, duration_ms, now, extra,
            )

        logger.warning("PipelineDB is not connected; cannot log audit event")
        return False

    def _direct_log_audit_event(
        self,
        api_key_id: Optional[str],
        user_role: Optional[str],
        method: str,
        path: str,
        status_code: Optional[int],
        request_body: Optional[str],
        ip_address: Optional[str],
        duration_ms: Optional[int],
        now: str,
        extra: dict[str, Any],
    ) -> bool:
        try:
            self._ensure_direct_connected()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO api_audit_log
                    (api_key_id, user_role, method, path, status_code,
                     request_body, ip_address, duration_ms, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    api_key_id,
                    user_role,
                    method[:16] if method else "",  # Truncate to column size
                    path[:512] if path else "",
                    status_code,
                    request_body,
                    ip_address,
                    duration_ms,
                    now,
                ),
            )
            cur.close()
            return True
        except Exception as exc:
            logger.warning("Failed to log audit event: %s", exc)
            return False

    def _rest_log_audit_event(
        self,
        api_key_id: Optional[str],
        user_role: Optional[str],
        method: str,
        path: str,
        status_code: Optional[int],
        request_body: Optional[str],
        ip_address: Optional[str],
        duration_ms: Optional[int],
        now: str,
        extra: dict[str, Any],
    ) -> bool:
        payload: dict[str, Any] = {
            "api_key_id": api_key_id,
            "user_role": user_role,
            "method": method[:16] if method else "",
            "path": path[:512] if path else "",
            "status_code": status_code,
            "request_body": request_body,
            "ip_address": ip_address,
            "duration_ms": duration_ms,
            "created_at": now,
        }
        payload.update(extra)
        result = self._rest_request("POST", _TABLE_AUDIT_LOG, data=payload)
        return result is not None

    # ── Bulk operations ───────────────────────────────────────────────

    def sync_from_filesystem(self, repo_root: str) -> dict[str, int]:
        """Scan the filesystem for datasets, outputs, and exports, syncing to DB.

        This is a best-effort operation. It walks the standard directory layout:
            subjects/datasets/{npc_key}/{technique}/train.jsonl
            subjects/datasets/{npc_key}/{technique}/train_clean.jsonl
            subjects/datasets/{npc_key}/{technique}/quality_summary.json
            subjects/datasets/{npc_key}/{technique}/quality_failures.json
            outputs/{npc_key}/runs/*/
            exports/{npc_key}/*.gguf

        Args:
            repo_root: Absolute path to the repository root.

        Returns:
            A dict with counts of created artifacts: {datasets: N, exports: N, runs: N}.
        """
        counts: dict[str, int] = {"datasets": 0, "exports": 0, "runs": 0}
        root = Path(repo_root)

        if not root.is_dir():
            logger.warning("sync_from_filesystem: %s is not a directory", repo_root)
            return counts

        # Scan datasets
        datasets_dir = root / "subjects" / "datasets"
        if datasets_dir.is_dir():
            for npc_dir in datasets_dir.iterdir():
                if not npc_dir.is_dir():
                    continue
                npc_key = npc_dir.name
                for technique_dir in npc_dir.iterdir():
                    if not technique_dir.is_dir():
                        continue
                    technique = technique_dir.name
                    train_path = technique_dir / "train.jsonl"
                    if train_path.is_file():
                        try:
                            file_size = train_path.stat().st_size
                            self.create_artifact(
                                npc_key=npc_key,
                                artifact_type="dataset",
                                file_path=str(train_path),
                                technique=technique,
                                file_size_bytes=file_size,
                                metadata={"file": "train.jsonl"},
                            )
                            counts["datasets"] += 1
                        except Exception:
                            pass

                    clean_path = technique_dir / "train_clean.jsonl"
                    if clean_path.is_file():
                        try:
                            file_size = clean_path.stat().st_size
                            self.create_artifact(
                                npc_key=npc_key,
                                artifact_type="dataset",
                                file_path=str(clean_path),
                                technique=technique,
                                file_size_bytes=file_size,
                                metadata={"file": "train_clean.jsonl"},
                            )
                            counts["datasets"] += 1
                        except Exception:
                            pass

        # Scan exports
        exports_dir = root / "exports"
        if exports_dir.is_dir():
            for npc_dir in exports_dir.iterdir():
                if not npc_dir.is_dir():
                    continue
                npc_key = npc_dir.name
                for gguf_file in npc_dir.glob("*.gguf"):
                    try:
                        file_size = gguf_file.stat().st_size
                        self.create_artifact(
                            npc_key=npc_key,
                            artifact_type="gguf",
                            file_path=str(gguf_file),
                            file_size_bytes=file_size,
                            metadata={
                                "filename": gguf_file.name,
                                "is_adapter": "-lora-" in gguf_file.name,
                            },
                        )
                        counts["exports"] += 1
                    except Exception:
                        pass

        # Scan outputs for run directories
        outputs_dir = root / "outputs"
        if outputs_dir.is_dir():
            for npc_dir in outputs_dir.iterdir():
                if not npc_dir.is_dir():
                    continue
                npc_key = npc_dir.name
                runs_dir = npc_dir / "runs"
                if runs_dir.is_dir():
                    for run_dir_entry in runs_dir.iterdir():
                        if not run_dir_entry.is_dir():
                            continue
                        run_id = run_dir_entry.name
                        meta_path = run_dir_entry / "meta.json"
                        if meta_path.is_file():
                            try:
                                meta = json.loads(meta_path.read_text())
                                self.create_run(
                                    npc_key=npc_key,
                                    run_id=run_id,
                                    run_dir=str(run_dir_entry),
                                    stage=meta.get("stage"),
                                    technique=meta.get("technique"),
                                    preset=meta.get("preset"),
                                    spec_path=meta.get("spec_path"),
                                    model=meta.get("model"),
                                    status=meta.get("status", "unknown"),
                                )
                                counts["runs"] += 1
                            except Exception:
                                pass

        logger.info(
            "sync_from_filesystem complete: %d datasets, %d exports, %d runs",
            counts["datasets"],
            counts["exports"],
            counts["runs"],
        )
        return counts

    # ── Connection lifecycle ──────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection if open."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as exc:
                logger.warning("Error closing DB connection: %s", exc)
            finally:
                self._conn = None

    def __enter__(self) -> "PipelineDB":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
