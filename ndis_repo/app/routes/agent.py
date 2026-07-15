from __future__ import annotations

from typing import Any, Literal
import logging
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from langsmith import traceable

from app.core.config import OLLAMA_CHAT_MODEL
from app.retrieve.hybrid import hybrid_search, lexical_candidate_ids

from app.inference.ollama_client import ollama_chat_completions
from app.inference.registry import resolve_provider_for_model

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger("app")


def _extract_name_like_query(query: str) -> str | None:
    """Best-effort extraction of a name/org phrase from the user query.

    This is intentionally heuristic: the goal is to bias retrieval toward
    chunks that are actually about the named entity, while the full query
    (e.g., "educational background") still drives the final ranking.
    """

    import re

    q = query or ""

    # Common patterns: "about <name>", "of <name>", "for <name>".
    m = re.search(
        r"\b(?:about|of|for)\s+([A-Za-z][A-Za-z\.'\-]*(?:\s+[A-Za-z][A-Za-z\.'\-]*){0,2})\b",
        q,
    )
    if not m:
        return None

    candidate = (m.group(1) or "").strip().strip('"').strip("'")
    if not candidate:
        return None

    # Remove common trailing education/background words if the regex captured too much.
    candidate = re.sub(
        r"\b(?:educational|education|background|study|studies|qualifications|degree|degrees)\b.*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip()

    # Avoid returning extremely short strings.
    if len(candidate) < 3:
        return None

    return candidate


class AgentRequest(BaseModel):
    query: str
    top_k: int = Field(default=4, ge=1, le=20)
    source_filter: str | None = None
    record_type: str | None = None
    alpha: float = Field(default=0.55, ge=0.0, le=1.0)
    context_mode: Literal["snippet", "full"] = Field(default="snippet")


class AgentResponse(BaseModel):
    answer: str
    retrieved_chunks: list[dict[str, Any]]


@traceable(run_type="llm")
@router.post("/answer", response_model=AgentResponse)
def answer(req: AgentRequest) -> AgentResponse:
    retrieval_start = time.perf_counter()
    # Bias retrieval toward chunks mentioning the named entity (best-effort),
    # then use the full query to refine ranking (e.g., educational background).
    name_like = _extract_name_like_query(req.query)
    candidate_ids: list[int] | None = None
    if name_like:
        # Fast first-stage candidate generation using FTS only (no embeddings).
        # This avoids making `/agent/answer` pay the embedding latency twice.
        candidate_ids = lexical_candidate_ids(
            query=name_like,
            top_k=min(15, req.top_k * 2),
            source_filter=req.source_filter,
            record_type=req.record_type,
        )

    if candidate_ids:
        retrieved = hybrid_search(
            query=req.query,
            top_k=req.top_k,
            source_filter=req.source_filter,
            record_type=req.record_type,
            alpha=req.alpha,
            candidate_chunk_ids=candidate_ids,
            require_fts=False,
        )

        # Safety: if constrained retrieval failed, rerun unconstrained.
        if not retrieved:
            retrieved = hybrid_search(
                query=req.query,
                top_k=req.top_k,
                source_filter=req.source_filter,
                record_type=req.record_type,
                alpha=req.alpha,
            )
    else:
        retrieved = hybrid_search(
            query=req.query,
            top_k=req.top_k,
            source_filter=req.source_filter,
            record_type=req.record_type,
            alpha=req.alpha,
        )

    retrieval_elapsed_ms = (time.perf_counter() - retrieval_start) * 1000
    # Manual pipeline tracking for the agent run.
    print(
        f"RETRIEVAL COMPLETE retrieved_chunks={len(retrieved)} elapsed_ms={retrieval_elapsed_ms:.1f}"
    )
    logger.info(
        "RETRIEVAL COMPLETE retrieved_chunks=%s elapsed_ms=%.1f",
        len(retrieved),
        retrieval_elapsed_ms,
    )

    context_lines: list[str] = []
    max_chunk_chars = 800
    for i, c in enumerate(retrieved, start=1):
        citation = c.get("citation") or {}
        doc_id = citation.get("document_id")
        section = citation.get("section")
        score = c.get("score")
        # Default is to send snippets to keep the prompt small.
        # Switch to `full` to send the entire chunk text.
        if req.context_mode == "full":
            context_piece = c.get("text") or ""
        else:
            context_piece = c.get("snippet") or ""

        if not isinstance(context_piece, str) or not context_piece.strip():
            # Fallback: if snippet is missing, still provide something.
            context_piece = c.get("text") or ""

        context_piece = (context_piece or "").strip()
        if len(context_piece) > max_chunk_chars:
            context_piece = context_piece[:max_chunk_chars] + "…"
        context_lines.append(
            f"[Chunk {i} | doc_id={doc_id} | section={section} | score={score}]\n{context_piece}"
        )

    context = "\n\n".join(context_lines)
    print(f"context:\n{context}")
    system = (
        "You are a grounded assistant. Answer the user using ONLY the provided context. "
        "If the context does not contain the answer, say you don't know and suggest what to ingest or refine."
        "If there are multiple document ids, make sure to find the relation between them, otherwise treat the information of diffrent document ids separately."
    )

    user = (
        f"Question: {req.query}\n\n"
        f"Context:\n{context or '(no relevant context retrieved)'}\n\n"
        "Return a concise answer."
    )

    provider = resolve_provider_for_model(OLLAMA_CHAT_MODEL)
    if provider.provider != "ollama":
        raise RuntimeError(f"Unsupported provider for agent: {provider.provider}")

    answer_text = ollama_chat_completions(
        model=provider.model_id,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return AgentResponse(answer=answer_text, retrieved_chunks=retrieved)
