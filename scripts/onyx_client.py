#!/usr/bin/env python3
"""Enhanced Onyx HTTP client for local retrieval, chat, agents, and ingestion.

This client wraps the Onyx backend API (FastAPI, proxied through nginx) and provides:
  - Search / Health (existing)
  - Chat API: sessions, messages with RAG grounding
  - Persona API: list, create, update assistant agents
  - Document Set API: create, list for scoping knowledge
  - Connector/Ingestion API: file upload, reindex triggers
  - Query API: tags
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import requests


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

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


def _find_onyx_api_key() -> str | None:
    """Find the Onyx API key from env, .env, or Hermes MCP config."""
    # Check env / .env first
    for key in ("ONYX_API_KEY",):
        val = os.environ.get(key)
        if val:
            return val
    file_env = _load_project_env()
    for key in ("ONYX_API_KEY",):
        val = file_env.get(key)
        if val:
            return val
    # Fall back: try Hermes config for onyx provider
    for cfg_path in (Path.home() / ".hermes" / "config.yaml", Path.home() / ".hermes" / "config.json"):
        if cfg_path.exists():
            for line in cfg_path.read_text().splitlines():
                if "onyx" in line.lower() and "api" in line.lower() and "key" in line.lower() and ":" in line:
                    _, val = line.split(":", 1)
                    clean = val.strip().strip('"').strip("'")
                    if clean and clean != "null":
                        return clean
    return None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

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


@dataclass
class OnyxPersona:
    id: int
    name: str
    description: str
    system_prompt: str | None = None
    task_prompt: str | None = None
    document_set_ids: list[int] = field(default_factory=list)
    tool_ids: list[int] = field(default_factory=list)
    is_public: bool = True
    datetime_aware: bool = True
    num_tools: int = 0
    num_document_sets: int = 0
    icon_name: str | None = None
    starter_messages: list[str] | None = None


@dataclass
class OnyxChatSession:
    id: str
    persona_id: int
    description: str | None = None
    temperature: float | None = None
    current_model: str | None = None


@dataclass
class OnyxDocumentSet:
    id: int
    name: str
    description: str
    is_public: bool = True


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class OnyxClient:
    """Enhanced client for the local Onyx API (FastAPI backend).

    All API paths are automatically prefixed with /api. Connects to
    nginx on port 80 by default. Authentication via Bearer token.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        search_mode: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        file_env = _load_project_env()
        self.base_url = (
            base_url
            or os.environ.get("ONYX_BASE_URL")
            or file_env.get("ONYX_BASE_URL")
            or "http://localhost"
        ).rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else _find_onyx_api_key()
        )
        self.timeout = float(
            timeout
            or os.environ.get("ONYX_TIMEOUT")
            or file_env.get("ONYX_TIMEOUT")
            or "30"
        )
        self.search_mode = (
            search_mode
            or os.environ.get("ONYX_SEARCH_MODE")
            or file_env.get("ONYX_SEARCH_MODE")
            or "admin"
        ).lower()
        if self.search_mode not in {"admin", "search"}:
            raise ValueError("ONYX_SEARCH_MODE must be 'admin' or 'search'")
        self.session = session or requests.Session()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api(self, path: str) -> str:
        """Prepend /api to the path if not already present."""
        path = path.lstrip("/")
        if path.startswith("api/"):
            return f"{self.base_url}/{path}"
        return f"{self.base_url}/api/{path}"

    @property
    def search_url(self) -> str:
        return f"/{'admin/' if self.search_mode == 'admin' else ''}search"

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict | list | None = None,
        params: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
        timeout: float | None = None,
        raw_response: bool = False,
    ) -> Any:
        """Make an HTTP request and return parsed JSON or raw response."""
        url = self._api(path)
        headers = self._headers()
        if files:
            # Let requests set the multipart boundary
            headers.pop("Content-Type", None)

        resp = self.session.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            params=params,
            files=files,
            timeout=timeout or self.timeout,
        )
        if raw_response:
            return resp
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct or resp.text.startswith(("{", "[")):
            return resp.json()
        return resp.text

    # ------------------------------------------------------------------
    # Health / Search
    # ------------------------------------------------------------------

    def health(self) -> bool:
        try:
            resp = self.session.get(
                self._api("/health"),
                timeout=min(self.timeout, 5),
            )
            return resp.status_code == 200
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
        payload: dict[str, Any] = {"query": query}
        if self.search_mode == "admin":
            payload["filters"] = {}
            if document_sets:
                payload["filters"]["metadata"] = {"npc_key": document_sets}
            if tags:
                payload["filters"]["tags"] = tags
        else:
            payload["skip_query_expansion"] = skip_query_expansion
            if document_sets:
                payload["document_sets"] = document_sets
            if tags:
                payload["tags"] = tags

        data = self._request("POST", self.search_url, json_body=payload)
        raw_results = data.get("results") or data.get("documents") or []
        return [self._normalize_result(item).as_dict() for item in raw_results[:max_results]]

    @staticmethod
    def _normalize_result(item: dict[str, Any]) -> OnyxSearchResult:
        citation_id = item.get("citation_id")
        document_id = item.get("document_id") or (
            f"citation:{citation_id}" if citation_id is not None else "unknown"
        )
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

    # ------------------------------------------------------------------
    # Server Info
    # ------------------------------------------------------------------

    def get_version(self) -> str:
        return self._request("GET", "/version").get("backend_version", "unknown")

    # ------------------------------------------------------------------
    # Persona API (Agents)
    # ------------------------------------------------------------------

    def list_personas(self) -> list[OnyxPersona]:
        data = self._request("GET", "/persona")
        return [
            OnyxPersona(
                id=p.get("id", 0),
                name=p.get("name", ""),
                description=p.get("description", ""),
                system_prompt=p.get("system_prompt"),
                task_prompt=p.get("task_prompt"),
                document_set_ids=p.get("document_set_ids") or [],
                tool_ids=[t["id"] for t in (p.get("tools") or [])],
                is_public=p.get("is_public", True),
                datetime_aware=p.get("datetime_aware", True),
                num_tools=len(p.get("tools") or []),
                num_document_sets=len(p.get("document_sets") or []),
                icon_name=p.get("icon_name"),
                starter_messages=p.get("starter_messages"),
            )
            for p in data
        ]

    def get_persona(self, persona_id: int) -> OnyxPersona | None:
        try:
            data = self._request("GET", f"/persona/{persona_id}")
            if isinstance(data, dict):
                return OnyxPersona(
                    id=data.get("id", persona_id),
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    system_prompt=data.get("system_prompt"),
                    task_prompt=data.get("task_prompt"),
                    document_set_ids=data.get("document_set_ids") or [],
                    tool_ids=[t["id"] for t in (data.get("tools") or [])],
                    is_public=data.get("is_public", True),
                    datetime_aware=data.get("datetime_aware", True),
                    num_tools=len(data.get("tools") or []),
                    num_document_sets=len(data.get("document_sets") or []),
                    icon_name=data.get("icon_name"),
                    starter_messages=data.get("starter_messages"),
                )
            return None
        except Exception:
            return None

    def create_persona(
        self,
        name: str,
        description: str,
        system_prompt: str,
        task_prompt: str = "",
        document_set_ids: list[int] | None = None,
        tool_ids: list[int] | None = None,
        is_public: bool = True,
        datetime_aware: bool = True,
        starter_messages: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "task_prompt": task_prompt,
            "document_set_ids": document_set_ids or [],
            "tool_ids": tool_ids or [1],  # default: internal_search
            "is_public": is_public,
            "datetime_aware": datetime_aware,
        }
        if starter_messages:
            payload["starter_messages"] = starter_messages
        return self._request("POST", "/persona", json_body=payload)

    def update_persona(self, persona_id: int, **kwargs: Any) -> dict[str, Any]:
        return self._request("PATCH", f"/persona/{persona_id}", json_body=kwargs)

    # ------------------------------------------------------------------
    # Chat API
    # ------------------------------------------------------------------

    def create_chat_session(
        self,
        persona_id: int,
        description: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"persona_id": persona_id}
        if description:
            payload["description"] = description
        return self._request("POST", "/chat/create-chat-session", json_body=payload)

    def send_message(
        self,
        message: str,
        persona_id: int = 0,
        chat_session_id: str | None = None,
        parent_message_id: str | None = None,
        file_descriptors: list[dict[str, Any]] | None = None,
        search_filters: dict[str, Any] | None = None,
        llm_override: dict[str, Any] | None = None,
        stream: bool = False,
        include_citations: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any] | Iterator[str]:
        payload: dict[str, Any] = {
            "message": message,
            "persona_id": persona_id,
            "include_citations": include_citations,
            "stream": stream,
        }
        if chat_session_id:
            payload["chat_session_id"] = chat_session_id
        if parent_message_id:
            payload["parent_message_id"] = parent_message_id
        if file_descriptors:
            payload["file_descriptors"] = file_descriptors
        if search_filters:
            payload["internal_search_filters"] = search_filters
        if llm_override:
            payload["llm_override"] = llm_override

        resp = self._request(
            "POST", "/chat/send-chat-message",
            json_body=payload,
            timeout=timeout or self.timeout,
            raw_response=True,
        )
        resp.raise_for_status()

        if stream:
            return self._stream_response(resp)
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            return resp.json()
        return {"response": resp.text}

    @staticmethod
    def _stream_response(resp: requests.Response) -> Iterator[str]:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    content = chunk.get("content") or chunk.get("token") or ""
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    def get_chat_sessions(self) -> list[OnyxChatSession]:
        data = self._request("GET", "/chat/get-user-chat-sessions")
        sessions = data if isinstance(data, list) else data.get("sessions", [])
        return [
            OnyxChatSession(
                id=s.get("id", ""),
                persona_id=s.get("persona_id", 0),
                description=s.get("description"),
                temperature=s.get("temperature"),
                current_model=s.get("current_model"),
            )
            for s in sessions
        ]

    def get_chat_session(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/chat/get-chat-session/{session_id}")
        except Exception:
            return None

    def delete_chat_session(self, session_id: str) -> bool:
        try:
            self._request("DELETE", f"/chat/delete-chat-session/{session_id}")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Document Set API
    # ------------------------------------------------------------------

    def list_document_sets(self) -> list[OnyxDocumentSet]:
        data = self._request("GET", "/manage/document-set")
        return [
            OnyxDocumentSet(
                id=ds.get("id", 0),
                name=ds.get("name", ""),
                description=ds.get("description", ""),
                is_public=ds.get("is_public", True),
            )
            for ds in data
        ]

    def create_document_set(
        self,
        name: str,
        description: str = "",
        is_public: bool = True,
        cc_pair_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Create a document set. cc_pair_ids is required by Onyx API.
        Pass an empty list to create an unlinked set (files can be added later).
        """
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "is_public": is_public,
        }
        if cc_pair_ids is not None:
            payload["cc_pair_ids"] = cc_pair_ids
        else:
            # Onyx requires cc_pair_ids; pass empty list to allow later linking
            payload["cc_pair_ids"] = []
        return self._request("POST", "/manage/admin/document-set", json_body=payload)

    # ------------------------------------------------------------------
    # Ingestion API (programmatic document push)
    # ------------------------------------------------------------------

    def ingest_document(
        self,
        doc_id: str,
        sections: list[dict[str, str]],
        semantic_identifier: str,
        metadata: dict[str, Any] | None = None,
        source: str = "ingestion_api",
        doc_updated_at: str | None = None,
    ) -> dict[str, Any]:
        """Push a document into Onyx via the Ingestion API.

        Args:
            doc_id: Unique document identifier.
            sections: List of dicts with 'text' (required) and optional 'link'.
            semantic_identifier: Human-readable title for the document.
            metadata: Dict with keys like source_type, table_name, npc_key, etc.
            source: Document source label (default: ingestion_api).
            doc_updated_at: ISO 8601 timestamp (default: now).

        Returns:
            Ingestion result with document_id and already_existed flag.
        """
        payload = {
            "document": {
                "id": doc_id,
                "sections": sections,
                "source": source,
                "semantic_identifier": semantic_identifier,
                "metadata": metadata or {},
                "from_ingestion_api": True,
            }
        }
        if doc_updated_at:
            payload["document"]["doc_updated_at"] = doc_updated_at
        return self._request("POST", "/onyx-api/ingestion", json_body=payload)

    def list_ingested_docs(self, source: str = "ingestion_api") -> list[dict[str, Any]]:
        """List documents ingested via the Onyx Ingestion API."""
        data = self._request("GET", "/onyx-api/ingestion")
        docs = data if isinstance(data, list) else data.get("documents", [])
        if source:
            docs = [d for d in docs if d.get("source") == source]
        return docs

    def delete_ingested_doc(self, doc_id: str) -> bool:
        """Delete an ingested document by ID."""
        try:
            self._request("DELETE", f"/onyx-api/ingestion/{doc_id}")
            return True
        except Exception:
            return False

    def ingest_supabase_table(
        self,
        npc_key: str,
        table_name: str,
        rows: list[dict[str, Any]],
        id_field: str = "id",
        text_fields: list[str] | None = None,
        semantic_template: str = "{npc_key} {table_name} record",
        link_template: str | None = None,
    ) -> list[dict[str, Any]]:
        """Ingest multiple rows from a Supabase table as Onyx documents.

        Each row becomes one document. The text_fields are concatenated
        to form the document body. Metadata includes npc_key and table_name
        for filtered searches.

        Args:
            npc_key: NPC identifier for metadata filtering.
            table_name: Supabase table name for metadata.
            rows: List of row dicts from Supabase.
            id_field: Field in each row to use as document ID.
            text_fields: Fields to include in the document text.
                         Defaults to all fields except id_field and timestamps.
            semantic_template: Template for semantic_identifier.
            link_template: Optional URL template per row.

        Returns:
            List of ingestion results.
        """
        results = []
        for row in rows:
            doc_id = f"supabase-{table_name}-{row.get(id_field, 'unknown')}-{npc_key}"
            row_id = row.get(id_field, "")

            # Build searchable text from specified fields or all non-metadata fields
            text_parts = []
            fields_to_include = text_fields or [k for k in row.keys()
                                                  if k not in (id_field, "created_at", "updated_at", "deleted_at")]
            for f in fields_to_include:
                val = row.get(f)
                if val is not None:
                    text_parts.append(f"{f}: {val}")

            sections = [{"text": "\n".join(text_parts)}]
            if link_template:
                sections[0]["link"] = link_template.format(**row)

            metadata = {
                "source_type": "supabase",
                "table_name": table_name,
                "npc_key": npc_key,
                "row_id": str(row_id),
            }

            semantic_id = semantic_template.format(npc_key=npc_key, table_name=table_name, **row)

            result = self.ingest_document(
                doc_id=doc_id,
                sections=sections,
                semantic_identifier=semantic_id,
                metadata=metadata,
            )
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Connector / Ingestion API
    # ------------------------------------------------------------------

    def list_connectors(self) -> list[dict[str, Any]]:
        return self._request("GET", "/manage/admin/connector")

    def upload_file(self, file_path: str) -> dict[str, Any]:
        """Upload a single file to Onyx for indexing.

        Args:
            file_path: Absolute path to the file.

        Returns:
            Response dict with upload result.
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            return {"file": file_path, "error": "File not found"}
        try:
            with open(file_path, "rb") as f:
                resp = self._request(
                    "POST",
                    "/manage/admin/connector/file/upload",
                    files={"files": (path_obj.name, f, "application/octet-stream")},
                    raw_response=True,
                )
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "application/json" in ct:
                return resp.json()
            return {"file": file_path, "status": "uploaded", "response": resp.text[:200]}
        except Exception as e:
            return {"file": file_path, "error": str(e)}

    def upload_files(self, file_paths: list[str]) -> list[dict[str, Any]]:
        """Upload multiple files. Returns results for each."""
        return [self.upload_file(fp) for fp in file_paths]

    def trigger_reindex(self, cc_pair_id: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if cc_pair_id is not None:
            payload["cc_pair_id"] = cc_pair_id
        return self._request("POST", "/manage/admin/indexing/targeted-reindex", json_body=payload)

    def get_index_job_status(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/manage/admin/indexing/targeted-reindex/{job_id}")

    def get_connector_status(self) -> list[dict[str, Any]]:
        return self._request("GET", "/manage/admin/connector/status")

    def list_indexed_sources(self) -> list[dict[str, Any]]:
        return self._request("GET", "/manage/indexed-sources")

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def get_valid_tags(self) -> list[dict[str, str]]:
        return self._request("GET", "/query/valid-tags")

    # ------------------------------------------------------------------
    # Convenience: NPC workflow helpers
    # ------------------------------------------------------------------

    def _discover_cc_pair_ids(self) -> list[int]:
        """Discover active cc_pair_ids from connector status."""
        try:
            status = self.get_connector_status()
            ids = []
            if isinstance(status, list):
                for s in status:
                    cp = s.get("cc_pair_id")
                    if cp is not None:
                        ids.append(int(cp))
            return ids
        except Exception:
            return []

    def ensure_npc_document_set(self, npc_key: str) -> OnyxDocumentSet:
        """Find or create a document set for a given NPC key.

        If creating, uses discovered cc_pair_ids from active connectors.
        """
        all_sets = self.list_document_sets()
        for ds in all_sets:
            if ds.name == npc_key:
                return ds
        # Discover cc_pair_ids from active connectors
        cc_pairs = self._discover_cc_pair_ids()
        if not cc_pairs:
            raise RuntimeError(
                "No active connectors found in Onyx. Cannot create document set "
                "without cc_pair_ids. Index some documents first (e.g., via GitHub connector)."
            )
        result = self.create_document_set(
            name=npc_key,
            description=f"Reference documents for NPC: {npc_key}",
            cc_pair_ids=cc_pairs,
        )
        raw_id = result.get("id") or (result if isinstance(result, (int, str)) else None)
        return OnyxDocumentSet(
            id=int(raw_id) if raw_id else 0,
            name=npc_key,
            description=f"Reference documents for NPC: {npc_key}",
            is_public=True,
        )

    def index_npc_reference_docs(
        self,
        npc_key: str,
        file_paths: list[str],
        wait_for_index: bool = False,
    ) -> list[dict[str, Any]]:
        """Upload reference documents for an NPC.

        Steps:
          1. Ensure a document set for the NPC exists.
          2. Upload each reference file.
          3. Optionally wait for indexing.

        Returns:
            List of upload results.
        """
        ds = self.ensure_npc_document_set(npc_key)
        print(f"[onyx] Document set '{npc_key}' (id={ds.id}) ready")

        results = self.upload_files(file_paths)
        for r in results:
            status = "OK" if "error" not in r else f"FAIL: {r.get('error')}"
            print(f"[onyx] Upload {Path(r['file']).name}: {status}")

        if wait_for_index and any("error" not in r for r in results):
            job = self.trigger_reindex()
            job_id = job.get("job_id") or job.get("id", "")
            print(f"[onyx] Reindex triggered: job_id={job_id}")
            if job_id:
                self._wait_for_index_job(job_id)

        return results

    def _wait_for_index_job(
        self, job_id: str, poll_interval: float = 3.0, max_wait: float = 120.0
    ) -> dict[str, Any]:
        start = time.monotonic()
        while time.monotonic() - start < max_wait:
            try:
                status = self.get_index_job_status(job_id)
                state = status.get("status") or status.get("state", "")
                print(f"[onyx] Reindex {job_id}: {state}")
                if state in ("completed", "finished", "success"):
                    return status
                if state in ("failed", "error"):
                    return status
            except Exception:
                pass
            time.sleep(poll_interval)
        print(f"[onyx] Reindex timed out after {max_wait}s")
        return {"job_id": job_id, "status": "timeout"}


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    client = OnyxClient()

    print(f"Onyx version: {client.get_version()}")
    print(f"Health: {client.health()}")

    # Personas
    personas = client.list_personas()
    print(f"\nPersonas ({len(personas)}):")
    for p in personas:
        print(f"  [{p.id}] {p.name}: system_prompt={'yes' if p.system_prompt else 'no'}, tools={p.num_tools}")

    # Document sets
    dsets = client.list_document_sets()
    print(f"\nDocument Sets ({len(dsets)}):")
    for ds in dsets:
        print(f"  [{ds.id}] {ds.name}")

    # Quick search
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        results = client.search(query, max_results=3)
        print(f"\nSearch '{query}': {len(results)} results")
        for r in results:
            print(f"  • {r['title']}: {r['content'][:80]}...")
