from __future__ import annotations

from typing import Literal

import psycopg
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.retrieve.hybrid import hybrid_search

router = APIRouter(prefix="/retrieve", tags=["retrieve"])


class Citation(BaseModel):
    document_id: int
    section: str | None = None
    offset_start: int | None = None
    offset_end: int | None = None
    record_id: int
    record_type: str
    record_title: str | None = None
    provenance_pointer: str | None = None


class RetrievedChunk(BaseModel):
    chunk_id: int
    record_id: int
    record_type: str
    score: float
    text: str
    snippet: str | None = None
    highlights: list[str] = []
    citation: Citation


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=4, ge=1, le=50)
    source_filter: str | None = None
    record_type: str | None = None
    # Weight of the semantic branch in hybrid retrieval. The lexical branch uses (1 - alpha).
    alpha: float = Field(default=0.55, ge=0.0, le=1.0)


@router.post("", response_model=list[RetrievedChunk])
def retrieve(req: RetrieveRequest):
    return hybrid_search(
        query=req.query,
        top_k=req.top_k,
        source_filter=req.source_filter,
        record_type=req.record_type,
        alpha=req.alpha,
    )
