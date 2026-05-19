"""
Debug router — LLM intelligence probe & RAG document management.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Depends
from pydantic import BaseModel

from ..auth import verify_admin
from ..services.llm_probe import LLMIntelligenceProbe
from ..services.rag_service import RAGService

router = APIRouter(prefix="/api/debug", tags=["debug"], dependencies=[Depends(verify_admin)])

_probe = LLMIntelligenceProbe()
_rag   = RAGService()

_SYSTEM_PROMPT = (
    Path(__file__).resolve().parents[1]
    .joinpath("prompts/citizen_assistant_system.txt")
    .read_text(encoding="utf-8")
)


@router.get("/llm-check")
async def llm_intelligence_check():
    """
    Run all LLM probe cases against the current Sarvam model.
    Returns a score (0–100), grade, and per-case results.
    """
    report = await _probe.run_all_probes(_SYSTEM_PROMPT)
    return report


class RAGDocInput(BaseModel):
    title: str
    content: str
    category: str
    language_code: str = "en-IN"
    source: str | None = None


@router.post("/rag/add")
async def add_rag_document(doc: RAGDocInput):
    """Add a knowledge document to the RAG store (requires pgvector + Sarvam)."""
    result = await _rag.add_document(
        title=doc.title,
        content=doc.content,
        category=doc.category,
        language_code=doc.language_code,
        source=doc.source,
    )
    if not result:
        raise HTTPException(status_code=503, detail="RAG not available — DB or Sarvam not configured.")
    return {"ok": True, "document": result}


@router.post("/rag/search")
async def search_rag(query: str = Body(..., embed=True), language_code: str = Body("en-IN", embed=True)):
    """Test the RAG retrieval for a given query."""
    chunks = await _rag.retrieve(query, language_code)
    return {"query": query, "chunks_found": len(chunks), "chunks": chunks}
