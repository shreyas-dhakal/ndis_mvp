from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from psycopg.rows import dict_row

from .chunking import ParsedRecord, chunk_text, classify_record_type
from .db import get_connection
from .embeddings import EmbeddingUnavailable, chat_completion, embed_query, embed_texts_async
from .config import RETRIEVAL_LEXICAL_CANDIDATES, RETRIEVAL_RRF_K, RETRIEVAL_SEMANTIC_CANDIDATES

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
UPLOADS_DIR = DATA_DIR / "uploads"


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.12f}" for value in values) + "]"


def _normalise_text(value: str) -> str:
    value = value.replace("\u00ad", "")
    value = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _read_plaintext(file_path: Path) -> str | None:
    if file_path.suffix.lower() not in {".txt", ".md", ".csv", ".json"}:
        return None
    return _normalise_text(file_path.read_text(encoding="utf-8", errors="ignore"))


def _parse_docling_document(dl_document) -> list[dict[str, str | None]]:
    blocks: list[dict[str, str | None]] = []
    atomic_labels = {"table", "picture", "formula"}
    heading_labels = {"section_header", "title", "page_header"}

    def flush(buffer_texts: list[str], title: str | None, section: str | None, page_no, ref):
        if not buffer_texts:
            return None
        merged = _normalise_text("\n".join(buffer_texts))
        if not merged:
            return None
        return {
            "title": title,
            "text": merged,
            "section": section,
            "provenance_pointer": f"docling://page/{page_no}/item/{ref}",
        }

    try:
        buffer_texts: list[str] = []
        buffer_title: str | None = None
        buffer_section: str | None = None
        buffer_page_no = None
        buffer_ref = None
        current_heading = None

        for item, _level in dl_document.iterate_items():
            label = getattr(item, "label", None)
            label_str = str(label.value if hasattr(label, "value") else label)
            prov = getattr(item, "prov", None)
            page_no = getattr(prov[0], "page_no", None) if prov else None
            section = f"page_{page_no}" if page_no is not None else "unknown"

            if label_str in atomic_labels:
                block = flush(buffer_texts, buffer_title, buffer_section, buffer_page_no, buffer_ref)
                if block:
                    blocks.append(block)
                buffer_texts, buffer_title = [], None

                if label_str == "table":
                    try:
                        text = item.export_to_markdown(dl_document)
                    except Exception:
                        text = getattr(item, "text", "") or ""
                else:
                    text = getattr(item, "text", "") or getattr(item, "caption", "") or ""

                text = _normalise_text(text)
                if text:
                    blocks.append(
                        {
                            "title": f"{label_str}" + (f" ({current_heading})" if current_heading else ""),
                            "text": text,
                            "section": section,
                            "provenance_pointer": f"docling://page/{page_no}/item/{item.self_ref}",
                        }
                    )
                continue

            if label_str in heading_labels:
                block = flush(buffer_texts, buffer_title, buffer_section, buffer_page_no, buffer_ref)
                if block:
                    blocks.append(block)
                buffer_texts, buffer_title = [], None
                current_heading = _normalise_text(getattr(item, "text", "") or "") or current_heading
                continue

            text = _normalise_text(getattr(item, "text", "") or "")
            if not text:
                continue

            buffer_texts.append(text)
            buffer_title = current_heading or label_str
            buffer_section = section
            buffer_page_no = page_no
            buffer_ref = item.self_ref

        block = flush(buffer_texts, buffer_title, buffer_section, buffer_page_no, buffer_ref)
        if block:
            blocks.append(block)
    except Exception:
        blocks = []

    return blocks


def _extract_blocks(file_path: Path) -> list[dict[str, str | None]]:
    plain_text = _read_plaintext(file_path)
    if plain_text:
        return [
            {
                "title": file_path.stem,
                "text": plain_text,
                "section": "full",
                "provenance_pointer": "file://full",
            }
        ]

    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Docling is not installed. Install backend dependencies before ingesting PDFs or DOCX files.",
        ) from exc

    try:
        dl_document = DocumentConverter().convert(str(file_path)).document
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Document parsing failed: {exc}") from exc

    blocks = _parse_docling_document(dl_document)
    if blocks:
        return blocks

    for method in ("export_to_text", "export_to_markdown"):
        if hasattr(dl_document, method):
            try:
                value = getattr(dl_document, method)()
            except Exception:
                continue
            if value and str(value).strip():
                return [
                    {
                        "title": file_path.stem,
                        "text": _normalise_text(str(value)),
                        "section": "full",
                        "provenance_pointer": "docling://document",
                    }
                ]

    raise HTTPException(status_code=400, detail="No extractable text found in document")


def _blocks_to_records(blocks: list[dict[str, str | None]]) -> list[ParsedRecord]:
    records: list[ParsedRecord] = []
    for block in blocks:
        content = (block.get("text") or "").strip()
        if not content:
            continue
        record_type = classify_record_type(content)
        records.append(
            ParsedRecord(
                record_type=record_type,
                title=block.get("title"),
                content=content,
                provenance_pointer=block.get("provenance_pointer"),
                section=block.get("section"),
                chunks=chunk_text(
                    content,
                    record_type=record_type,
                    section=block.get("section"),
                    provenance_pointer=block.get("provenance_pointer"),
                    title=block.get("title"),
                ),
            )
        )
    return records


def _tokenize_terms(query: str) -> list[str]:
    terms = [value.lower() for value in re.split(r"\W+", query or "") if value.strip()]
    stop_words = {"the", "and", "or", "to", "of", "in", "a", "an", "for", "is", "are", "be"}
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if len(term) < 3 or term in stop_words or term in seen:
            continue
        seen.add(term)
        out.append(term)
    return out


def _make_snippet(text: str, query: str, *, radius: int = 180) -> tuple[str | None, list[str]]:
    text = text or ""
    terms = _tokenize_terms(query)
    if not text.strip() or not terms:
        return None, []

    lowered = text.lower()
    best_index = None
    matched: list[str] = []
    for term in terms:
        index = lowered.find(term)
        if index == -1:
            continue
        matched.append(term)
        if best_index is None or index < best_index:
            best_index = index

    if best_index is None:
        snippet = text[: min(len(text), radius * 2)].strip()
        return (snippet + "..." if len(text) > len(snippet) else snippet), []

    start = max(0, best_index - radius)
    end = min(len(text), best_index + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet, matched[:6]


def _rrf(rank: int, *, weight: float) -> float:
    return weight * (1.0 / (RETRIEVAL_RRF_K + rank))


def _note_text(note_dict: dict[str, Any]) -> str:
    labels = {
        "subjective": "Subjective",
        "objective": "Objective",
        "assessment": "Assessment",
        "plan": "Plan",
        "participant_voice": "Participant Voice",
        "support_type": "Support Type",
        "risks_incidents": "Risks / Incidents",
    }
    lines: list[str] = []
    for key, label in labels.items():
        value = note_dict.get(key)
        if value:
            lines.append(f"{label}: {value}")
    goals = note_dict.get("linked_goals") or []
    if goals:
        lines.append("Linked Goals: " + ", ".join(str(goal) for goal in goals))
    consent = note_dict.get("consent_noted")
    if consent is not None:
        lines.append(f"Consent Noted: {'Yes' if consent else 'No'}")
    return "\n".join(lines)


async def ingest_upload(
    *,
    file: UploadFile,
    source: str = "local",
    author: str = "user",
    doc_type: str = "document",
) -> dict[str, Any]:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    storage_name = f"{uuid.uuid4().hex}_{file.filename}"
    storage_path = UPLOADS_DIR / storage_name
    storage_path.write_bytes(file_bytes)

    blocks = _extract_blocks(storage_path)
    records = _blocks_to_records(blocks)
    if not records:
        raise HTTPException(status_code=400, detail="No records could be derived from the uploaded file")

    all_chunks = [chunk for record in records for chunk in record.chunks]
    embeddings: list[list[float] | None] = [None] * len(all_chunks)
    if all_chunks:
        try:
            embedded = await embed_texts_async([chunk.chunk_text for chunk in all_chunks])
        except EmbeddingUnavailable:
            embedded = []
        if embedded:
            embeddings = embedded

    sha256 = hashlib.sha256(file_bytes).hexdigest()

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into documents (source, original_filename, mime_type, sha256, storage_path, metadata)
                values (%s, %s, %s, %s, %s, %s)
                returning id, created_at
                """,
                [
                    source,
                    file.filename,
                    file.content_type,
                    sha256,
                    str(storage_path),
                    json.dumps({"doc_type": doc_type}),
                ],
            )
            document_row = cur.fetchone()
            document_id = str(document_row["id"])

            chunk_position = 0
            for record in records:
                cur.execute(
                    """
                    insert into records (
                        document_id,
                        record_type,
                        status,
                        body,
                        source,
                        author,
                        title,
                        content,
                        provenance_pointer,
                        metadata,
                        tsv
                    )
                    values (
                        %s,
                        %s,
                        'confirmed',
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        to_tsvector('english', coalesce(%s, ''))
                    )
                    returning id
                    """,
                    [
                        document_id,
                        record.record_type,
                        json.dumps(
                            {
                                "title": record.title,
                                "content": record.content,
                                "section": record.section,
                                "provenance_pointer": record.provenance_pointer,
                            }
                        ),
                        source,
                        author,
                        record.title,
                        record.content,
                        record.provenance_pointer,
                        json.dumps({"doc_type": doc_type, "ingest_source": "upload"}),
                        record.content,
                    ],
                )
                record_id = str(cur.fetchone()["id"])

                for chunk in record.chunks:
                    embedding = embeddings[chunk_position] if chunk_position < len(embeddings) else None
                    cur.execute(
                        """
                        insert into chunks (
                            record_id,
                            document_id,
                            record_type,
                            section,
                            offset_start,
                            offset_end,
                            chunk_index,
                            chunk_text,
                            chunk_metadata,
                            embedding,
                            tsv
                        )
                        values (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s::vector,
                            to_tsvector('english', coalesce(%s, ''))
                        )
                        """,
                        [
                            record_id,
                            document_id,
                            record.record_type,
                            chunk.section,
                            chunk.offset_start,
                            chunk.offset_end,
                            chunk.chunk_index,
                            chunk.chunk_text,
                            json.dumps({**chunk.chunk_metadata, "source": source}),
                            _vector_literal(embedding) if embedding else None,
                            chunk.chunk_text,
                        ],
                    )
                    chunk_position += 1

            conn.commit()

    return {
        "document_id": document_id,
        "records_created": len(records),
        "chunks_created": len(all_chunks),
        "embedding_status": "ready" if any(embeddings) else "lexical_only",
    }


def list_documents() -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  d.id,
                  d.original_filename,
                  d.mime_type,
                  d.metadata->>'doc_type' as doc_type,
                  d.created_at,
                  (select count(*) from records r where r.document_id = d.id) as records_count,
                  (select count(*) from chunks c where c.document_id = d.id) as chunks_count
                from documents d
                order by d.created_at desc
                """
            )
            rows = cur.fetchall()

    return [
        {
            "document_id": str(row["id"]),
            "id": str(row["id"]),
            "name": row.get("original_filename") or "Untitled",
            "original_filename": row.get("original_filename"),
            "mime_type": row.get("mime_type"),
            "doc_type": row.get("doc_type"),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "records_count": int(row.get("records_count") or 0),
            "chunks_count": int(row.get("chunks_count") or 0),
        }
        for row in rows
    ]


def delete_document(document_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("delete from documents where id = %s returning id, storage_path", [document_id])
            row = cur.fetchone()
            conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    storage_path = row.get("storage_path")
    if storage_path and os.path.exists(storage_path):
        os.remove(storage_path)

    return {"deleted": True, "document_id": str(row["id"])}


def _build_chunk_filters(
    *,
    source_filter: str | None,
    record_type: str | None,
    candidate_chunk_ids: list[str] | None,
    require_embedding: bool,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if require_embedding:
        clauses.append("c.embedding is not null")
    if source_filter:
        clauses.append("c.chunk_metadata->>'source' = %s")
        params.append(source_filter)
    if record_type:
        clauses.append("c.record_type = %s")
        params.append(record_type)
    if candidate_chunk_ids is not None:
        clauses.append("c.id = any(%s::uuid[])")
        params.append(candidate_chunk_ids)
    return (" where " + " and ".join(clauses)) if clauses else "", params


def _semantic_candidates(
    *,
    query_vec: list[float],
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    candidate_chunk_ids: list[str] | None,
) -> list[dict[str, Any]]:
    where_sql, params = _build_chunk_filters(
        source_filter=source_filter,
        record_type=record_type,
        candidate_chunk_ids=candidate_chunk_ids,
        require_embedding=True,
    )
    candidate_limit = max(top_k * 8, RETRIEVAL_SEMANTIC_CANDIDATES)
    sql = f"""
        select c.id, c.embedding <=> %s::vector as sem_distance
        from chunks c
        {where_sql}
        order by c.embedding <=> %s::vector asc
        limit %s
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [_vector_literal(query_vec), *params, _vector_literal(query_vec), candidate_limit])
            return cur.fetchall()


def _lexical_candidates(
    *,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    candidate_chunk_ids: list[str] | None,
) -> list[dict[str, Any]]:
    clauses = ["c.tsv @@ websearch_to_tsquery('english', %s)"]
    params: list[Any] = [query]
    if source_filter:
        clauses.append("c.chunk_metadata->>'source' = %s")
        params.append(source_filter)
    if record_type:
        clauses.append("c.record_type = %s")
        params.append(record_type)
    if candidate_chunk_ids is not None:
        clauses.append("c.id = any(%s::uuid[])")
        params.append(candidate_chunk_ids)

    candidate_limit = max(top_k * 8, RETRIEVAL_LEXICAL_CANDIDATES)
    sql = f"""
        select c.id, ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) as lex_rank
        from chunks c
        where {' and '.join(clauses)}
        order by ts_rank_cd(c.tsv, websearch_to_tsquery('english', %s)) desc
        limit %s
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [query, *params, query, candidate_limit])
            return cur.fetchall()


def _fetch_chunk_payloads(chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not chunk_ids:
        return {}
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  c.id,
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
                join records r on r.id = c.record_id
                where c.id = any(%s::uuid[])
                """,
                [chunk_ids],
            )
            rows = cur.fetchall()
    return {str(row["id"]): row for row in rows}


def lexical_candidate_ids(
    *,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
) -> list[str]:
    clauses = ["c.tsv @@ plainto_tsquery('english', %s)"]
    params: list[Any] = [query]
    if source_filter:
        clauses.append("c.chunk_metadata->>'source' = %s")
        params.append(source_filter)
    if record_type:
        clauses.append("c.record_type = %s")
        params.append(record_type)

    sql = f"""
        select c.id
        from chunks c
        where {' and '.join(clauses)}
        order by ts_rank_cd(c.tsv, plainto_tsquery('english', %s)) desc
        limit %s
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [*params, query, top_k])
            return [str(row["id"]) for row in cur.fetchall()]


def retrieve_chunks(
    *,
    query: str,
    top_k: int = 4,
    source_filter: str | None = None,
    record_type: str | None = None,
    alpha: float = 0.55,
    candidate_chunk_ids: list[str] | None = None,
    require_fts: bool = True,
) -> list[dict[str, Any]]:
    semantic_rows: list[dict[str, Any]] = []
    try:
        query_vec = embed_query(query)
    except EmbeddingUnavailable:
        query_vec = None

    if query_vec is not None:
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

    semantic_weight = alpha if semantic_rows else 0.0
    lexical_weight = 1.0 - alpha if semantic_rows else 1.0
    fused_scores: dict[str, float] = {}
    for rank, row in enumerate(semantic_rows, start=1):
        chunk_id = str(row["id"])
        fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + _rrf(rank, weight=semantic_weight)
    for rank, row in enumerate(lexical_rows, start=1):
        chunk_id = str(row["id"])
        fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + _rrf(rank, weight=lexical_weight)

    chunk_ids = [
        chunk_id
        for chunk_id, _score in sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    ]
    payloads = _fetch_chunk_payloads(chunk_ids)

    out: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        row = payloads.get(chunk_id)
        if row is None:
            continue
        snippet, highlights = _make_snippet(row.get("chunk_text") or "", query)
        out.append(
            {
                "chunk_id": chunk_id,
                "record_id": str(row["record_id"]),
                "record_type": row["record_type"],
                "score": float(fused_scores.get(chunk_id, 0.0)),
                "text": row["chunk_text"],
                "snippet": snippet,
                "highlights": highlights,
                "citation": {
                    "document_id": str(row["document_id"]) if row.get("document_id") else None,
                    "section": row.get("section"),
                    "offset_start": row.get("offset_start"),
                    "offset_end": row.get("offset_end"),
                    "record_id": str(row["record_id"]),
                    "record_type": row["record_type"],
                    "record_title": row.get("record_title"),
                    "provenance_pointer": row.get("provenance_pointer"),
                },
            }
        )
    return out


def _extract_name_like_query(query: str) -> str | None:
    match = re.search(
        r"\b(?:about|of|for)\s+([A-Za-z][A-Za-z\.'\-]*(?:\s+[A-Za-z][A-Za-z\.'\-]*){0,2})\b",
        query or "",
    )
    if not match:
        return None
    candidate = (match.group(1) or "").strip().strip('"').strip("'")
    candidate = re.sub(
        r"\b(?:educational|education|background|study|studies|qualifications|degree|degrees)\b.*$",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip()
    return candidate if len(candidate) >= 3 else None


def answer_question(
    *,
    query: str,
    top_k: int = 4,
    source_filter: str | None = None,
    record_type: str | None = None,
    alpha: float = 0.55,
    context_mode: str = "snippet",
) -> dict[str, Any]:
    candidate_ids = None
    name_like = _extract_name_like_query(query)
    if name_like:
        candidate_ids = lexical_candidate_ids(
            query=name_like,
            top_k=min(15, top_k * 2),
            source_filter=source_filter,
            record_type=record_type,
        )

    retrieved = retrieve_chunks(
        query=query,
        top_k=top_k,
        source_filter=source_filter,
        record_type=record_type,
        alpha=alpha,
        candidate_chunk_ids=candidate_ids,
        require_fts=not bool(candidate_ids),
    )
    if candidate_ids and not retrieved:
        retrieved = retrieve_chunks(
            query=query,
            top_k=top_k,
            source_filter=source_filter,
            record_type=record_type,
            alpha=alpha,
        )

    if not retrieved:
        return {
            "answer": "I couldn't find anything relevant in the stored documents yet. Upload documents or try a more specific question.",
            "retrieved_chunks": [],
        }

    context_lines: list[str] = []
    for index, chunk in enumerate(retrieved, start=1):
        citation = chunk.get("citation") or {}
        context_piece = chunk.get("text") if context_mode == "full" else chunk.get("snippet")
        context_piece = (context_piece or chunk.get("text") or "").strip()
        context_lines.append(
            f"[Chunk {index} | document_id={citation.get('document_id')} | section={citation.get('section')} | score={chunk.get('score')}]\n{context_piece[:800]}"
        )
    context = "\n\n".join(context_lines)

    try:
        answer = chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a grounded NDIS assistant. Answer only using the supplied context. "
                        "If the context is insufficient, say you do not know and suggest what document to ingest next."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nContext:\n{context}\n\nReturn a concise answer.",
                },
            ]
        )
    except Exception:
        # Keep chat usable for demos even if the local chat model is offline.
        answer = "\n".join(
            ["Relevant evidence found:"]
            + [f"- {(chunk.get('snippet') or chunk.get('text') or '').strip()}" for chunk in retrieved[:3]]
        )

    return {"answer": answer, "retrieved_chunks": retrieved}


async def store_generated_note(note_dict: dict[str, Any], thread_id: str) -> tuple[str, str]:
    note_text = _note_text(note_dict)
    embedding = None
    if note_text.strip():
        try:
            embedding = (await embed_texts_async([note_text]))[0]
        except (EmbeddingUnavailable, IndexError):
            embedding = None

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                insert into records (
                    record_type,
                    status,
                    body,
                    source,
                    author,
                    title,
                    content,
                    metadata,
                    tsv
                )
                values (
                    'note',
                    'confirmed',
                    %s,
                    %s,
                    'support_worker',
                    %s,
                    %s,
                    %s,
                    to_tsvector('english', coalesce(%s, ''))
                )
                returning id, created_at
                """,
                [
                    json.dumps(note_dict),
                    f"thread:{thread_id}",
                    "Generated NDIS progress note",
                    note_text,
                    json.dumps({"origin": "note_generator", "thread_id": thread_id}),
                    note_text,
                ],
            )
            row = cur.fetchone()
            record_id = str(row["id"])
            created_at = row["created_at"].isoformat()
            if note_text.strip():
                cur.execute(
                    """
                    insert into chunks (
                        record_id,
                        record_type,
                        section,
                        offset_start,
                        offset_end,
                        chunk_index,
                        chunk_text,
                        chunk_metadata,
                        embedding,
                        tsv
                    )
                    values (
                        %s,
                        'note',
                        'generated_note',
                        0,
                        %s,
                        0,
                        %s,
                        %s,
                        %s::vector,
                        to_tsvector('english', coalesce(%s, ''))
                    )
                    """,
                    [
                        record_id,
                        len(note_text),
                        note_text,
                        json.dumps({"source": f"thread:{thread_id}", "origin": "note_generator"}),
                        _vector_literal(embedding) if embedding else None,
                        note_text,
                    ],
                )
            conn.commit()
    return record_id, created_at
