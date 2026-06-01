#!/usr/bin/env python3
"""Standalone HTTP REST API client for Confident AI.

Wraps the Confident AI REST API (https://api.confident-ai.com/v1) for
remote evaluation and dataset management.  Uses only stdlib modules —
no third-party dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from src.core.ops import env_loader

__all__ = [
    "ConfidentAPIClient",
    "confident_available",
    "get_confident_client",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ConfidentAPIClient:
    """HTTP REST client for the Confident AI API (https://api.confident-ai.com/v1).

    Parameters
    ----------
    api_key : str, optional
        Confident AI API key.  When omitted, the client reads
        ``CONFIDENT_API_KEY`` from the environment (via ``env_loader``
        which sources ``.env.local`` automatically).

    Raises
    ------
    EnvironmentError
        If no key is provided and ``CONFIDENT_API_KEY`` is not set in the
        environment.
    """

    BASE_URL = "https://api.confident-ai.com/v1"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = self._resolve_api_key(api_key)

    # ------------------------------------------------------------------
    # Public API — Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        test_cases: list[dict[str, Any]],
        metric_collection: dict[str, Any],
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """Submit a batch of LLM test cases for remote evaluation.

        Parameters
        ----------
        test_cases : list[dict]
            A list of test-case dicts.  Each dict must contain at least
            ``input`` and ``actualOutput``.
        metric_collection : dict
            Describes which metrics to evaluate.  Must contain ``name``
            and ``include`` (a list of metric-name strings).
        identifier : str, optional
            Optional label to identify this evaluation run.

        Returns
        -------
        dict
            ``{"success": bool, "data": {"testRunId": str}}``
        """
        body: dict[str, Any] = {
            "metricCollection": metric_collection,
            "llmTestCases": test_cases,
            "hyperparameters": {},
        }
        if identifier is not None:
            body["identifier"] = identifier
        return self._request("POST", "/evaluate", body)

    def evaluate_conversational(
        self,
        test_cases: list[dict[str, Any]],
        metric_collection: dict[str, Any],
        identifier: str | None = None,
    ) -> dict[str, Any]:
        """Submit multi-turn conversational test cases for evaluation.

        Parameters
        ----------
        test_cases : list[dict]
            Conversational test-case dicts (structure differs from
            ``evaluate`` — uses ``conversationalTestCases``).
        metric_collection : dict
            Describes which metrics to evaluate.
        identifier : str, optional
            Optional label for this evaluation run.

        Returns
        -------
        dict
            ``{"success": bool, "data": {"testRunId": str}}``
        """
        body: dict[str, Any] = {
            "metricCollection": metric_collection,
            "conversationalTestCases": test_cases,
            "hyperparameters": {},
        }
        if identifier is not None:
            body["identifier"] = identifier
        return self._request("POST", "/evaluate", body)

    # ------------------------------------------------------------------
    # Public API — Datasets
    # ------------------------------------------------------------------

    def push_dataset(
        self,
        alias: str,
        goldens: list[dict[str, Any]],
        version: str | None = None,
        finalized: bool = True,
    ) -> dict[str, Any]:
        """Create or update a dataset identified by *alias*.

        Parameters
        ----------
        alias : str
            Dataset alias (e.g. ``"npc-dataset-history-guide-template"``).
        goldens : list[dict]
            Golden test cases to store.
        version : str, optional
            Semantic version string (e.g. ``"1.0.0"``).
        finalized : bool
            Whether the dataset is finalised for use (default ``True``).

        Returns
        -------
        dict
            The API response (typically ``{"success": bool, ...}``).
        """
        body: dict[str, Any] = {
            "finalized": finalized,
            "goldens": goldens,
        }
        if version is not None:
            body["version"] = version
        return self._request("POST", f"/datasets/{alias}", body)

    def pull_dataset(self, alias: str) -> list[dict[str, Any]]:
        """Retrieve goldens for a dataset by alias.

        Returns
        -------
        list[dict]
            The golden test cases stored under this alias.
        """
        result: dict[str, Any] = self._request("GET", f"/datasets/{alias}")
        return result.get("goldens", result.get("data", result))

    def list_datasets(self) -> list[dict[str, Any]]:
        """List all datasets.

        Returns
        -------
        list[dict]
            Metadata for each dataset.
        """
        result: dict[str, Any] = self._request("GET", "/datasets")
        return result.get("datasets", result.get("data", result))

    def delete_dataset(self, alias: str) -> bool:
        """Delete a dataset by alias.

        Returns
        -------
        bool
            ``True`` if deletion succeeded.
        """
        self._request("DELETE", f"/datasets/{alias}")
        return True

    def create_dataset_version(
        self, alias: str, goldens: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Create a new version of an existing dataset.

        Parameters
        ----------
        alias : str
            Dataset alias.
        goldens : list[dict]
            Golden test cases for this version.

        Returns
        -------
        dict
            The API response.
        """
        body: dict[str, Any] = {"goldens": goldens}
        return self._request("POST", f"/datasets/{alias}/versions", body)

    def list_dataset_versions(self, alias: str) -> list[dict[str, Any]]:
        """List all versions of a dataset.

        Returns
        -------
        list[dict]
            Version metadata for each version.
        """
        result: dict[str, Any] = self._request(
            "GET", f"/datasets/{alias}/versions"
        )
        return result.get("versions", result.get("data", result))

    # ------------------------------------------------------------------
    # Public API — Test Runs
    # ------------------------------------------------------------------

    def get_test_run(self, test_run_id: str) -> dict[str, Any]:
        """Retrieve a single test run by ID.

        Parameters
        ----------
        test_run_id : str
            The UUID of the test run (returned by ``evaluate()``).

        Returns
        -------
        dict
            Test-run details including metric results.
        """
        return self._request("GET", f"/test-runs/{test_run_id}")

    def list_test_runs(self) -> list[dict[str, Any]]:
        """List all test runs.

        Returns
        -------
        list[dict]
            Metadata for each test run.
        """
        result: dict[str, Any] = self._request("GET", "/test-runs")
        return result.get("data", result.get("testRuns", result))

    def list_test_runs_paginated(
        self, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """List test runs with pagination.

        Parameters
        ----------
        page : int
            Page number (1-indexed).
        page_size : int
            Items per page (default 20).

        Returns
        -------
        dict
            Paginated response containing ``items`` (or ``data``) and
            ``total`` count.
        """
        return self._request(
            "GET", f"/test-runs?page={page}&pageSize={page_size}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_api_key(provided: str | None) -> str:
        """Return the first available API key from argument or environment.

        Raises
        ------
        EnvironmentError
            If no key is provided and ``CONFIDENT_API_KEY`` is unset.
        """
        if provided is not None:
            return provided
        # Source .env.local before checking os.environ
        env_loader.ensure_confident_api_key(strict=False)
        key = os.environ.get("CONFIDENT_API_KEY")
        if not key or not key.strip():
            raise EnvironmentError(
                "CONFIDENT_API_KEY environment variable is not set.\n"
                "  Export it:  export CONFIDENT_API_KEY='your-key-here'\n"
                "  Or log in:  deepeval login\n"
                "  Get a key:  https://app.confident-ai.com/profile"
            )
        return key.strip()

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        """Execute an HTTP request against the Confident AI API.

        Parameters
        ----------
        method : str
            HTTP method (``GET``, ``POST``, ``DELETE``, etc.).
        path : str
            URL path relative to ``BASE_URL`` (e.g. ``/evaluate``).
        body : dict, optional
            JSON-serialisable request body for ``POST`` / ``PUT``.

        Returns
        -------
        Any
            The parsed JSON response (``dict`` or ``list``).

        Raises
        ------
        ValueError
            On 400 or 422 responses.
        PermissionError
            On 401 or 403 responses.
        FileNotFoundError
            On 404 responses.
        RuntimeError
            On 409, 5xx, or network errors.
        """
        url = f"{self.BASE_URL}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                parsed: Any = json.loads(raw)
                return parsed
        except urllib.error.HTTPError as exc:
            status = exc.code
            body_text = exc.read().decode("utf-8", errors="replace")
            self._raise_for_status(status, body_text, path)
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Network error connecting to Confident AI API at {url}: "
                f"{exc.reason}"
            ) from exc

    @staticmethod
    def _raise_for_status(status: int, body: str, path: str) -> None:
        """Parse an HTTP error body and raise the appropriate exception.

        Always raises — never returns normally.
        """
        error: dict[str, Any] | str = body
        try:
            error = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            pass

        msg: str | dict[str, Any] = error

        if status == 400:
            raise ValueError(f"Bad request: {msg}")
        if status == 401:
            raise PermissionError(
                "Confident AI API key invalid or expired. "
                "Run `deepeval login` or check CONFIDENT_API_KEY."
            )
        if status == 403:
            raise PermissionError(
                "Access forbidden. Check API key permissions."
            )
        if status == 404:
            raise FileNotFoundError(f"Resource not found: {path}")
        if status == 409:
            raise RuntimeError(f"Conflict: {msg}")
        if status == 422:
            raise ValueError(f"Unprocessable: {msg}")
        if 500 <= status < 600:
            raise RuntimeError(f"Server error ({status}): {msg}")

        raise RuntimeError(f"HTTP {status}: {msg}")


# ---------------------------------------------------------------------------
# Module-level convenience helpers
# ---------------------------------------------------------------------------


def get_confident_client() -> ConfidentAPIClient:
    """Get a :class:`ConfidentAPIClient` instance.

    Reads the API key from the environment via :func:`env_loader.ensure_confident_api_key`,
    which sources ``.env.local`` automatically.
    """
    return ConfidentAPIClient()


def confident_available() -> bool:
    """Check whether Confident AI credentials are configured.

    Returns ``True`` if ``CONFIDENT_API_KEY`` is set in the environment.
    Does **not** verify the key is valid — only that it is present.
    This function can be called without initialising the client.
    """
    return env_loader.confident_available()
