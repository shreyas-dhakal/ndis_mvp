from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from psycopg_pool import ConnectionPool

from .config import DATABASE_URL, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE, EMBEDDING_DIM

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            kwargs={"autocommit": False},
        )
    return _pool


@contextmanager
def get_connection():
    with get_pool().connection() as conn:
        yield conn


def ensure_schema() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "spine_schema.sql"
    sql = schema_path.read_text(encoding="utf-8").replace("{{EMBEDDING_DIM}}", str(EMBEDDING_DIM))
    with get_connection() as conn:
        conn.execute(sql)
        conn.commit()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
