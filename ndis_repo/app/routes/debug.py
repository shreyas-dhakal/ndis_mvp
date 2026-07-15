from fastapi import APIRouter

from psycopg.rows import dict_row

from app.db.pgvector_adapter import connect

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/stats")
def stats() -> dict[str, int]:
    with connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select
                  (select count(*) from documents) as documents_count,
                  (select count(*) from records) as records_count,
                  (select count(*) from chunks) as chunks_count
                """
            )
            row = cur.fetchone() or {}
    return {
        "documents_count": int(row.get("documents_count") or 0),
        "records_count": int(row.get("records_count") or 0),
        "chunks_count": int(row.get("chunks_count") or 0),
    }
