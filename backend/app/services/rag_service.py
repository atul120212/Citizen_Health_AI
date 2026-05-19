"""
RAG Service — Retrieval-Augmented Generation using pgvector + Sarvam embeddings.

Workflow:
  1. Embed the user query using Sarvam /embeddings API
  2. Cosine-similarity search on `nhm_documents.embedding`
  3. Return top-k chunks to be injected into the LLM system prompt
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from .. import db
from ..config import get_settings

logger = logging.getLogger(__name__)

# Maximum number of RAG chunks to inject per turn
TOP_K = 3
# Minimum similarity threshold (cosine distance < this → skip)
SIM_THRESHOLD = 0.6


class RAGService:
    _model = None

    def __init__(self) -> None:
        self.settings = get_settings()

    @classmethod
    def get_model(cls):
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading local embedding model: all-MiniLM-L6-v2 (this may take a few seconds)...")
                cls._model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Successfully loaded local embedding model: all-MiniLM-L6-v2")
            except Exception as e:
                logger.error("Failed to load sentence-transformers model: %s", e)
                cls._model = None
        return cls._model

    @property
    def model(self):
        return self.get_model()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(self, query: str, language_code: str = "en-IN") -> list[dict[str, Any]]:
        """
        Returns up to TOP_K relevant document chunks for the given query.
        Falls back to an empty list if pgvector or embeddings are unavailable.
        """
        if not db.is_configured():
            return []

        try:
            embedding = await self._embed(query)
            if embedding:
                return await self._search(embedding, language_code)
            else:
                return await self._text_search(query, language_code)
        except Exception as exc:
            logger.warning("RAG retrieve failed: %s", exc)
            return await self._text_search(query, language_code)

    async def add_document(
        self,
        title: str,
        content: str,
        category: str,
        language_code: str = "en-IN",
        source: str | None = None,
    ) -> dict[str, Any] | None:
        """Embed and store a document chunk in the nhm_documents table."""
        if not db.is_configured():
            return None
        embedding = await self._embed(content)
        if not embedding:
            return None
        vec_str = f"[{','.join(str(v) for v in embedding)}]"
        return await db.fetch_one(
            """
            INSERT INTO nhm_documents (title, content, category, language_code, source, embedding)
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (title, language_code) DO UPDATE
              SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
            RETURNING id, title, category, language_code
            """,
            (title, content, category, language_code, source, vec_str),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> list[float] | None:
        """Use local sentence-transformers model."""
        if not self.model:
            return None
        try:
            import asyncio
            # Encoding can be CPU intensive, run in executor
            loop = asyncio.get_running_loop()
            embeddings = await loop.run_in_executor(None, self.model.encode, text)
            return embeddings.tolist()
        except Exception as exc:
            logger.warning("Local embedding failed: %s", exc)
            return None

    async def _search(self, embedding: list[float], language_code: str) -> list[dict[str, Any]]:
        """pgvector cosine similarity search."""
        vec_str = f"[{','.join(str(v) for v in embedding)}]"
        # Search matching language first, fall back to en-IN
        rows = await db.fetch_all(
            """
            SELECT id, title, content, category, source,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM nhm_documents
            WHERE language_code = %s OR language_code = 'en-IN'
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vec_str, language_code, vec_str, TOP_K),
        )
        return [r for r in rows if (r.get("similarity") or 0) >= SIM_THRESHOLD]

    async def _text_search(self, query: str, language_code: str) -> list[dict[str, Any]]:
        """Fallback text search if embeddings are not available."""
        if not db.is_configured():
            return []
        words = [w for w in query.split() if len(w) > 3]
        if not words:
            return []
            
        conditions = " OR ".join(["content ILIKE %s" for _ in words])
        params = [f"%{w}%" for w in words]
        
        query_sql = f"""
            SELECT id, title, content, category, source
            FROM nhm_documents
            WHERE (language_code = %s OR language_code = 'en-IN')
            AND ({conditions})
            LIMIT {TOP_K}
        """
        return await db.fetch_all(query_sql, [language_code] + params)

    def format_context(self, chunks: list[dict[str, Any]]) -> str:
        """Format retrieved chunks as a context block for the system prompt."""
        if not chunks:
            return ""
        lines = ["--- RELEVANT KNOWLEDGE BASE ---"]
        for i, chunk in enumerate(chunks, 1):
            lines.append(f"[{i}] {chunk['title']} ({chunk['category']})")
            lines.append(chunk["content"])
        lines.append("--- END KNOWLEDGE BASE ---")
        return "\n".join(lines)
