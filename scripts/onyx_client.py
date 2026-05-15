#!/usr/bin/env python3
"""Small Onyx HTTP client for local retrieval-backed dataset generation.

The client intentionally uses only the public `/api/search` endpoint so dataset
creation can consume an existing local Onyx index without re-indexing or loading
extra models on the training box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


def _load_project_env() -> dict[str, str]:
    """Read simple KEY=VALUE pairs from the repo .env without overriding os.environ."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class OnyxSearchResult:
    document_id: str
    chunk_ind: int | None
    title: str
    content: str
    link: str | None
    source_type: str | None
    score: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_ind": self.chunk_ind,
            "title": self.title,
            "content": self.content,
            "link": self.link,
            "source_type": self.source_type,
            "score": self.score,
        }


class OnyxClient:
    """Resource-conscious client for local Onyx search.

    Defaults target a local Docker Onyx install exposed through nginx on port 80.
    API auth is optional because local deployments vary; set ONYX_API_KEY when
    your server requires a bearer token. If environment variables are absent,
    a project-root `.env` file is read so `./ucore` works without manual source.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        search_mode: str | None = None,
        session: Any | None = None,
    ) -> None:
        file_env = _load_project_env()
        self.base_url = (base_url or os.environ.get("ONYX_BASE_URL") or file_env.get("ONYX_BASE_URL") or "http://localhost").rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("ONYX_API_KEY") or file_env.get("ONYX_API_KEY")
        self.timeout = float(timeout or os.environ.get("ONYX_TIMEOUT") or file_env.get("ONYX_TIMEOUT") or "20")
        self.search_mode = (search_mode or os.environ.get("ONYX_SEARCH_MODE") or file_env.get("ONYX_SEARCH_MODE") or "admin").lower()
        if self.search_mode not in {"admin", "search"}:
            raise ValueError("ONYX_SEARCH_MODE must be 'admin' or 'search'")
        self.session = session or requests.Session()

    @property
    def search_url(self) -> str:
        path = "/api/admin/search" if self.search_mode == "admin" else "/api/search"
        return f"{self.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/api/health", timeout=min(self.timeout, 5))
            return response.status_code == 200
        except Exception:
            return False

    def search(
        self,
        query: str,
        max_results: int = 4,
        document_sets: list[str] | None = None,
        tags: list[dict[str, str]] | None = None,
        skip_query_expansion: bool = True,
    ) -> list[dict[str, Any]]:
        """Search Onyx and return normalized result dicts.

        `max_results` is applied client-side because Onyx's `/api/search` schema
        does not expose a stable top-k field in the current local OpenAPI spec.
        """
        payload: dict[str, Any] = {
            "query": query,
            "skip_query_expansion": skip_query_expansion,
        }
        if self.search_mode == "admin":
            payload = {"query": query, "filters": {}}
        if document_sets:
            payload["document_sets" if self.search_mode == "search" else "filters"] = (
                document_sets if self.search_mode == "search" else {"document_set": document_sets}
            )
        if tags:
            if self.search_mode == "search":
                payload["tags"] = tags
            else:
                payload.setdefault("filters", {})["tags"] = tags

        response = self.session.post(
            self.search_url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        raw_results = data.get("results") or data.get("documents") or []
        return [self._normalize_result(item).as_dict() for item in raw_results[:max_results]]

    @staticmethod
    def _normalize_result(item: dict[str, Any]) -> OnyxSearchResult:
        citation_id = item.get("citation_id")
        document_id = item.get("document_id") or (f"citation:{citation_id}" if citation_id is not None else "unknown")
        chunk_ind = item.get("chunk_ind")
        content = item.get("content") or item.get("blurb") or ""
        title = item.get("title") or item.get("semantic_identifier") or document_id
        return OnyxSearchResult(
            document_id=str(document_id),
            chunk_ind=chunk_ind if isinstance(chunk_ind, int) else None,
            title=str(title),
            content=str(content),
            link=item.get("link"),
            source_type=str(item.get("source_type")) if item.get("source_type") is not None else None,
            score=item.get("score") if isinstance(item.get("score"), (int, float)) else None,
        )
