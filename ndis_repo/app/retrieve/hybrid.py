from __future__ import annotations

import logging
import time
from typing import Any

from psycopg.rows import dict_row

from app.core.config import (
    RETRIEVAL_LEXICAL_CANDIDATES,
    RETRIEVAL_RRF_K,
    RETRIEVAL_SEMANTIC_CANDIDATES,
)
from app.db.pgvector_adapter import connect
from app.inference.embeddings import embed_query
from app.core.langsmith_tracing import maybe_traceable


logger = logging.getLogger("app")


def _tokenize_query_terms(query: str) -> list[str]:
    import re

    terms = [t.lower() for t in re.split(r"\W+", query or "") if t.strip()]
    # Avoid extremely common/short tokens that create noisy highlights.
    stop = {"the", "and", "or", "to", "of", "in", "a", "an", "for", "is", "are", "be"}
    out: list[str] = []
    for t in terms:
        if len(t) < 3:
            continue
        if t in stop:
            continue
        out.append(t)
    # Keep order but dedupe.
    seen = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _make_snippet(
    *, text: str, query: str, snippet_radius: int = 180
) -> tuple[str | None, list[str]]:
    text = text or ""
    terms = _tokenize_query_terms(query)
    if not text.strip() or not terms:
        return None, []

    text_l = text.lower()
    best_idx = None
    matched_terms: list[str] = []
    for term in terms:
        idx = text_l.find(term)
        if idx == -1:
            continue
        matched_terms.append(term)
        if best_idx is None or idx < best_idx:
            best_idx = idx

    if best_idx is None:
        # No literal matches; fall back to a prefix snippet.
        snippet = text[: min(len(text), snippet_radius * 2)]
        snippet = snippet.strip()
        return (snippet + "…" if len(text) > len(snippet) else snippet), []

    start = max(0, best_idx - snippet_radius)
    end = min(len(text), best_idx + snippet_radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet, matched_terms[:6]




def _build_chunk_filters(
    *,
    source_filter: str | None,
    record_type: str | None,
    candidate_chunk_ids: list[int] | None,
) -> tuple[str, list[Any]]:
    where_clauses = ["c.embedding is not null"]
    params: list[Any] = []

    if source_filter is not None:
        where_clauses.append("c.chunk_metadata->>'source' = %s")
        params.append(source_filter)
    if record_type is not None:
        where_clauses.append("c.record_type = %s")
        params.append(record_type)
    if candidate_chunk_ids is not None:
        where_clauses.append("c.chunk_id = any(%s::bigint[])")
        params.append(candidate_chunk_ids)

    return " where " + " and ".join(where_clauses), params


def _semantic_candidates(
    *,
    query_vec: list[float],
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    candidate_chunk_ids: list[int] | None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_chunk_filters(
        source_filter=source_filter,
        record_type=record_type,
        candidate_chunk_ids=candidate_chunk_ids,
    )
    candidate_limit = max(top_k * 8, RETRIEVAL_SEMANTIC_CANDIDATES)
    sql = f"""
    select
      c.chunk_id,
      c.embedding <=> %s::vector as sem_distance
    from chunks c
    {where_sql}
    order by c.embedding <=> %s::vector asc
    limit %s
    """

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [query_vec, *params, query_vec, candidate_limit])
            return cur.fetchall()


def _lexical_candidates(
    *,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    candidate_chunk_ids: list[int] | None,
) -> list[dict[str, Any]]:
    where_clauses = ["c.tsv @@ websearch_to_tsquery('english', %s)"]
    filter_params: list[Any] = []
    if source_filter is not None:
        where_clauses.append("c.chunk_metadata->>'source' = %s")
        filter_params.append(source_filter)
    if record_type is not None:
        where_clauses.append("c.record_type = %s")
        filter_params.append(record_type)
    if candidate_chunk_ids is not None:
        where_clauses.append("c.chunk_id = any(%s::bigint[])")
        filter_params.append(candidate_chunk_ids)

    candidate_limit = max(top_k * 8, RETRIEVAL_LEXICAL_CANDIDATES)
    sql = f"""
    select
      c.chunk_id,
      ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) as lex_rank
    from chunks c
    where {' and '.join(where_clauses)}
    order by ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) desc
    limit %s
    """

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                sql,
                [query, query, *filter_params, query, candidate_limit],
            )
            return cur.fetchall()


def _rrf_score(rank: int, *, weight: float) -> float:
    return weight * (1.0 / (RETRIEVAL_RRF_K + rank))


def _fused_chunk_ids(
    *,
    lexical_rows: list[dict[str, Any]],
    semantic_rows: list[dict[str, Any]],
    alpha: float,
    top_k: int,
) -> tuple[list[int], dict[int, float]]:
    semantic_weight = alpha
    lexical_weight = 1.0 - alpha
    fused_scores: dict[int, float] = {}

    for rank, row in enumerate(semantic_rows, start=1):
        chunk_id = int(row["chunk_id"])
        fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + _rrf_score(
            rank, weight=semantic_weight
        )

    for rank, row in enumerate(lexical_rows, start=1):
        chunk_id = int(row["chunk_id"])
        fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + _rrf_score(
            rank, weight=lexical_weight
        )

    ordered_ids = [
        chunk_id
        for chunk_id, _score in sorted(
            fused_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]
    ]
    return ordered_ids, fused_scores


def _fetch_chunk_payloads(chunk_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not chunk_ids:
        return {}

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  c.chunk_id,
                  c.record_id,
                  c.record_type,
                  c.chunk_text,
                  c.section,
                  c.offset_start,
                  c.offset_end,
                  r.document_id,
                  r.title as record_title,
                  r.provenance_pointer
                from chunks c
                join records r on r.record_id = c.record_id
                where c.chunk_id = any(%s::bigint[])
                """,
                [chunk_ids],
            )
            rows = cur.fetchall()

    return {int(row["chunk_id"]): row for row in rows}


@maybe_traceable(name="hybrid_search", run_type="retriever")
def hybrid_search(
    *,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    alpha: float,
    candidate_chunk_ids: list[int] | None = None,
    require_fts: bool = True,
) -> list[dict[str, Any]]:
    overall_start = time.perf_counter()
    embed_start = time.perf_counter()
    query_vec = embed_query(query)
    embed_elapsed_ms = (time.perf_counter() - embed_start) * 1000

    sql_start = time.perf_counter()
    semantic_rows = _semantic_candidates(
        query_vec=query_vec,
        top_k=top_k,
        source_filter=source_filter,
        record_type=record_type,
        candidate_chunk_ids=candidate_chunk_ids,
    )
    lexical_rows = (
        _lexical_candidates(
            query=query,
            top_k=top_k,
            source_filter=source_filter,
            record_type=record_type,
            candidate_chunk_ids=candidate_chunk_ids,
        )
        if require_fts
        else []
    )
    chunk_ids, fused_scores = _fused_chunk_ids(
        lexical_rows=lexical_rows,
        semantic_rows=semantic_rows,
        alpha=alpha,
        top_k=top_k,
    )
    rows_by_id = _fetch_chunk_payloads(chunk_ids)
    sql_elapsed_ms = (time.perf_counter() - sql_start) * 1000

    if not chunk_ids:
        return []

    snippet_start = time.perf_counter()
    snippet_cache: dict[int, tuple[str | None, list[str]]] = {}

    out: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        row = rows_by_id.get(chunk_id)
        if row is None:
            continue
        if chunk_id not in snippet_cache:
            snippet_cache[chunk_id] = _make_snippet(
                text=row.get("chunk_text") or "",
                query=query,
            )
        snippet, highlights = snippet_cache[chunk_id]
        out.append(
            {
                "chunk_id": chunk_id,
                "record_id": row["record_id"],
                "record_type": row["record_type"],
                "score": float(fused_scores.get(chunk_id, 0.0)),
                "text": row["chunk_text"],
                "snippet": snippet,
                "highlights": highlights,
                "citation": {
                    "document_id": int(row["document_id"]),
                    "section": row["section"],
                    "offset_start": row["offset_start"],
                    "offset_end": row["offset_end"],
                    "record_id": row["record_id"],
                    "record_type": row["record_type"],
                    "record_title": row.get("record_title"),
                    "provenance_pointer": row.get("provenance_pointer"),
                },
            }
        )
    snippet_elapsed_ms = (time.perf_counter() - snippet_start) * 1000
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "hybrid_search timing (query_len=%s top_k=%s require_fts=%s candidate_ids=%s) embed=%.1fms sql=%.1fms post=%.1fms total=%.1fms",
            len(query or ""),
            top_k,
            require_fts,
            bool(candidate_chunk_ids),
            embed_elapsed_ms,
            sql_elapsed_ms,
            snippet_elapsed_ms,
            (time.perf_counter() - overall_start) * 1000,
        )
    return out


def lexical_candidate_ids(
    *,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
) -> list[int]:
    """Fast candidate generation using only Postgres FTS.

    Intentionally embedding-free: avoids the dominant latency of calling
    Ollama embeddings during the `/agent/answer` two-stage retrieval.

    Returns only chunk_ids (minimal payload).
    """

    where_clauses = ["c.tsv @@ plainto_tsquery('english', %s)"]
    params: list[Any] = []
    if source_filter is not None:
        where_clauses.append("c.chunk_metadata->>'source' = %s")
        params.append(source_filter)
    if record_type is not None:
        where_clauses.append("c.record_type = %s")
        params.append(record_type)

    where_sql = " where " + " and ".join(where_clauses)

    sql = f"""
    select c.chunk_id
    from chunks c
    {where_sql}
    order by ts_rank_cd(c.tsv, plainto_tsquery('english', %s)) desc
    limit %s
    """

    # Params order matches placeholders:
    # - where: %s (query)
    # - optional filters: source_filter, record_type
    # - order by: %s (query)
    # - limit: %s (top_k)
    final_params = [query, *params, query, top_k]

    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, final_params)
            rows = cur.fetchall()

    return [int(r["chunk_id"]) for r in rows]
