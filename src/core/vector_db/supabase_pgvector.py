#!/usr/bin/env python3
"""Supabase pgvector integration for semantic search and RAG.

Provides vector storage and retrieval using Supabase's pgvector extension.
Supports embedding generation via Ollama or Sentence Transformers.

Usage:
    from src.core.vector_db.supabase_pgvector import SupabaseVectorDB, get_embedder

    db = SupabaseVectorDB(
        url="http://localhost:54321",
        key="...",
        table="lore_documents"
    )

    embedder = get_embedder(model="nomic-embed-text:latest", backend="ollama")
    embedding = embedder.embed("historical fact")

    docs = db.search("What happened to Rome?", embedding_fn=embedder.embed, top_k=5)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "SupabaseVectorDB",
    "EmbeddingModel",
    "OllamaEmbedder",
    "get_embedder",
    "Document",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Document:
    """Represents a retrieved document from vector DB."""

    id: str
    content: str
    metadata: dict[str, Any]
    embedding: list[float] | None = None
    similarity_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "similarity_score": self.similarity_score,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Embedding Models
# ─────────────────────────────────────────────────────────────────────────────


class EmbeddingModel(ABC):
    """Abstract base for embedding models."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""
        pass

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Dimension of the embedding vectors."""
        pass


class OllamaEmbedder(EmbeddingModel):
    """Embedding model backed by Ollama (e.g., nomic-embed-text)."""

    def __init__(
        self,
        model: str = "nomic-embed-text:latest",
        base_url: str = "http://localhost:11434",
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dim: int | None = None

        # Lazy import to avoid hard dependency
        try:
            import ollama

            self.client = ollama.Client(base_url=self.base_url)
        except ImportError:
            raise ImportError(
                "ollama package required for OllamaEmbedder. Install: pip install ollama"
            )

    def embed(self, text: str) -> list[float]:
        """Embed text via Ollama."""
        resp = self.client.embeddings(model=self.model, prompt=text)
        embedding = resp.get("embedding", [])
        if not self._dim and embedding:
            self._dim = len(embedding)
        return embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts (sequentially via Ollama)."""
        embeddings = []
        for text in texts:
            embeddings.append(self.embed(text))
        return embeddings

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension (cached after first embed)."""
        if self._dim is None:
            # Probe with empty embed
            test_emb = self.embed("")
            self._dim = len(test_emb) if test_emb else 768
        return self._dim


class SentenceTransformerEmbedder(EmbeddingModel):
    """Embedding model backed by Sentence Transformers."""

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        self.model_name = model
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model)
        except ImportError:
            raise ImportError(
                "sentence-transformers required. Install: pip install sentence-transformers"
            )

    def embed(self, text: str) -> list[float]:
        """Embed text via Sentence Transformers."""
        embedding = self.model.encode([text], convert_to_tensor=False)
        return embedding[0].tolist() if len(embedding) > 0 else []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts (batched)."""
        embeddings = self.model.encode(texts, convert_to_tensor=False)
        return [e.tolist() for e in embeddings]

    @property
    def embedding_dim(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()


def get_embedder(
    model: str | None = None,
    backend: str = "ollama",
) -> EmbeddingModel:
    """Factory to get an embedder by name and backend.

    Parameters
    ----------
    model : str, optional
        Model name. Defaults depend on backend:
        - ollama: "nomic-embed-text:latest"
        - sentence-transformers: "all-MiniLM-L6-v2"
    backend : str
        "ollama" or "sentence-transformers"

    Returns
    -------
    EmbeddingModel
        Configured embedder.
    """
    if backend == "ollama":
        model = model or "nomic-embed-text:latest"
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaEmbedder(model=model, base_url=base_url)
    elif backend == "sentence-transformers":
        model = model or "all-MiniLM-L6-v2"
        return SentenceTransformerEmbedder(model=model)
    else:
        raise ValueError(f"Unknown embedding backend: {backend}")


# ─────────────────────────────────────────────────────────────────────────────
# Vector Database
# ─────────────────────────────────────────────────────────────────────────────


class SupabaseVectorDB:
    """Vector database backed by Supabase pgvector.

    Supports semantic search, upsert, and delete operations on documents.
    """

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        table: str = "documents",
    ):
        """Initialize Supabase vector DB client.

        Parameters
        ----------
        url : str, optional
            Supabase project URL. Defaults to SUPABASE_URL env var.
        key : str, optional
            Supabase anon/service key. Defaults to SUPABASE_KEY env var.
        table : str
            Table name to store documents (default "documents").
        """
        self.url = url or os.environ.get("SUPABASE_URL")
        self.key = key or os.environ.get("SUPABASE_KEY")
        self.table = table

        if not self.url or not self.key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_KEY required. "
                "Set via env vars or pass to __init__."
            )

        try:
            from supabase import create_client

            self.client = create_client(self.url, self.key)
        except ImportError:
            raise ImportError("supabase package required. Install: pip install supabase")

        logger.info(f"SupabaseVectorDB initialized: table={table}")

    def upsert(
        self,
        documents: list[Document],
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> list[str]:
        """Upsert documents with embeddings.

        Parameters
        ----------
        documents : list[Document]
            Documents to store.
        embedding_fn : callable, optional
            Function to generate embeddings (required if doc.embedding is None).

        Returns
        -------
        list[str]
            IDs of inserted/updated documents.
        """
        rows = []
        for doc in documents:
            # Generate embedding if not provided
            if doc.embedding is None:
                if embedding_fn is None:
                    raise ValueError(
                        "embedding_fn required when Document.embedding is None"
                    )
                doc.embedding = embedding_fn(doc.content)

            rows.append(
                {
                    "id": doc.id,
                    "content": doc.content,
                    "metadata": json.dumps(doc.metadata),
                    "embedding": doc.embedding,
                }
            )

        response = self.client.table(self.table).upsert(rows).execute()
        logger.info(f"Upserted {len(rows)} documents")
        return [r["id"] for r in response.data]

    def search(
        self,
        query: str,
        embedding_fn: Callable[[str], list[float]],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[Document]:
        """Search for similar documents.

        Parameters
        ----------
        query : str
            Query text.
        embedding_fn : callable
            Function to embed the query.
        top_k : int
            Number of results to return.
        threshold : float
            Similarity threshold (0-1). Documents below this are filtered out.

        Returns
        -------
        list[Document]
            Retrieved documents with similarity scores.
        """
        query_embedding = embedding_fn(query)

        # Use Supabase RPC for vector similarity search
        response = self.client.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": top_k,
            },
        ).execute()

        docs = []
        for row in response.data:
            doc = Document(
                id=row["id"],
                content=row["content"],
                metadata=json.loads(row.get("metadata", "{}")),
                similarity_score=row.get("similarity", None),
            )
            docs.append(doc)

        logger.info(f"Found {len(docs)} similar documents for query: {query[:50]}")
        return docs

    def delete(self, doc_id: str) -> bool:
        """Delete a document by ID.

        Parameters
        ----------
        doc_id : str
            Document ID to delete.

        Returns
        -------
        bool
            True if deleted, False if not found.
        """
        response = self.client.table(self.table).delete().eq("id", doc_id).execute()
        logger.info(f"Deleted document: {doc_id}")
        return len(response.data) > 0

    def list_all(self) -> list[Document]:
        """List all documents in the table.

        Returns
        -------
        list[Document]
            All documents.
        """
        response = self.client.table(self.table).select("*").execute()
        docs = [
            Document(
                id=row["id"],
                content=row["content"],
                metadata=json.loads(row.get("metadata", "{}")),
            )
            for row in response.data
        ]
        logger.info(f"Retrieved {len(docs)} documents from table")
        return docs

    def clear(self) -> None:
        """Delete all documents from the table."""
        self.client.table(self.table).delete().neq("id", "").execute()
        logger.info(f"Cleared all documents from table: {self.table}")
