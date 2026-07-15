from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg.rows import dict_row

from app.db.pgvector_adapter import connect

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    document_id: int
    original_filename: str | None
    mime_type: str | None
    doc_type: str | None
    records_count: int
    chunks_count: int


@router.get("", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  d.document_id,
                  d.original_filename,
                  d.mime_type,
                  d.metadata->>'doc_type' as doc_type,
                  (select count(*) from records r where r.document_id = d.document_id) as records_count,
                  (select count(*) from chunks c where c.document_id = d.document_id) as chunks_count
                from documents d
                order by d.document_id desc
                """
            )
            rows = cur.fetchall()

    return [
        DocumentSummary(
            document_id=int(r["document_id"]),
            original_filename=r.get("original_filename"),
            mime_type=r.get("mime_type"),
            doc_type=r.get("doc_type"),
            records_count=int(r.get("records_count") or 0),
            chunks_count=int(r.get("chunks_count") or 0),
        )
        for r in rows
    ]


class DeleteResponse(BaseModel):
    deleted: bool
    document_id: int


@router.delete("/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: int) -> DeleteResponse:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                delete from documents
                where document_id = %s
                returning document_id
                """,
                [document_id],
            )
            row: dict[str, Any] | None = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return DeleteResponse(deleted=True, document_id=int(row["document_id"]))
