from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any

from psycopg_pool import ConnectionPool

from .config import AGE_ENABLED, AGE_GRAPH_NAME, DATABASE_URL, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE, EMBEDDING_DIM

_pool: ConnectionPool | None = None
_age_supported: bool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=DB_POOL_MIN_SIZE,
            max_size=DB_POOL_MAX_SIZE,
            # Disable server-side prepared statements for compatibility with
            # transaction-pooled Postgres frontends such as PgBouncer.
            kwargs={"autocommit": False, "prepare_threshold": None},
        )
    return _pool


@contextmanager
def get_connection():
    with get_pool().connection() as conn:
        yield conn


def _cypher_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=True)


def _age_session_ready(conn) -> bool:
    global _age_supported
    if not AGE_ENABLED:
        return False
    if _age_supported is False:
        return False
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT age_session")
        try:
            cur.execute("LOAD 'age'")
            cur.execute('SET search_path = ag_catalog, "$user", public')
        except Exception:
            _age_supported = False
            cur.execute("ROLLBACK TO SAVEPOINT age_session")
            cur.execute("RELEASE SAVEPOINT age_session")
            return False
        cur.execute("RELEASE SAVEPOINT age_session")
    _age_supported = True
    return True


def age_available(conn) -> bool:
    return _age_session_ready(conn)


def _run_cypher(conn, query: str) -> None:
    if not _age_session_ready(conn):
        return
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM ag_catalog.cypher(%s, %s) AS (result agtype)",
            [AGE_GRAPH_NAME, query],
        )


def _fetch_cypher_values(conn, query: str, column_name: str) -> list[str]:
    if not _age_session_ready(conn):
        return []
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {column_name}::text AS value FROM ag_catalog.cypher(%s, %s) AS ({column_name} agtype)",
            [AGE_GRAPH_NAME, query],
        )
        rows = cur.fetchall()
    values: list[str] = []
    for row in rows:
        raw = row[0]
        if raw is None:
            continue
        value = str(raw).strip().strip('"')
        if value:
            values.append(value)
    return values


def ensure_age_graph(conn) -> None:
    if not _age_session_ready(conn):
        return
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s", [AGE_GRAPH_NAME])
        if cur.fetchone() is None:
            cur.execute("SELECT ag_catalog.create_graph(%s)", [AGE_GRAPH_NAME])
    conn.commit()


def sync_entity_node(conn, *, entity_id: str, entity_type: str, display_name: str) -> None:
    _run_cypher(
        conn,
        (
            f"MERGE (e:Entity {{id: {_cypher_literal(entity_id)}}}) "
            f"SET e.entity_type = {_cypher_literal(entity_type)}, "
            f"e.display_name = {_cypher_literal(display_name)} "
            "RETURN e"
        ),
    )


def sync_document_node(
    conn,
    *,
    document_id: str,
    source: str,
    original_filename: str | None,
) -> None:
    _run_cypher(
        conn,
        (
            f"MERGE (d:Document {{id: {_cypher_literal(document_id)}}}) "
            f"SET d.source = {_cypher_literal(source)}, "
            f"d.original_filename = {_cypher_literal(original_filename)} "
            "RETURN d"
        ),
    )


def sync_record_node(
    conn,
    *,
    record_id: str,
    record_type: str,
    title: str | None,
) -> None:
    _run_cypher(
        conn,
        (
            f"MERGE (r:Record {{id: {_cypher_literal(record_id)}}}) "
            f"SET r.record_type = {_cypher_literal(record_type)}, "
            f"r.title = {_cypher_literal(title)} "
            "RETURN r"
        ),
    )


def sync_entity_document_edge(conn, *, entity_id: str, document_id: str, relation_type: str) -> None:
    _run_cypher(
        conn,
        (
            f"MATCH (e:Entity {{id: {_cypher_literal(entity_id)}}}), "
            f"(d:Document {{id: {_cypher_literal(document_id)}}}) "
            f"MERGE (e)-[rel:HAS_DOCUMENT {{relation_type: {_cypher_literal(relation_type)}}}]->(d) "
            "RETURN rel"
        ),
    )


def sync_entity_record_edge(conn, *, entity_id: str, record_id: str, relation_type: str) -> None:
    _run_cypher(
        conn,
        (
            f"MATCH (e:Entity {{id: {_cypher_literal(entity_id)}}}), "
            f"(r:Record {{id: {_cypher_literal(record_id)}}}) "
            f"MERGE (e)-[rel:HAS_RECORD {{relation_type: {_cypher_literal(relation_type)}}}]->(r) "
            "RETURN rel"
        ),
    )


def sync_document_record_edge(conn, *, document_id: str, record_id: str) -> None:
    _run_cypher(
        conn,
        (
            f"MATCH (d:Document {{id: {_cypher_literal(document_id)}}}), "
            f"(r:Record {{id: {_cypher_literal(record_id)}}}) "
            "MERGE (d)-[rel:CONTAINS_RECORD]->(r) "
            "RETURN rel"
        ),
    )


def sync_record_link(conn, *, from_record_id: str, to_record_id: str, link_type: str) -> None:
    _run_cypher(
        conn,
        (
            f"MATCH (from_record:Record {{id: {_cypher_literal(from_record_id)}}}), "
            f"(to_record:Record {{id: {_cypher_literal(to_record_id)}}}) "
            f"MERGE (from_record)-[rel:LINKED_TO {{link_type: {_cypher_literal(link_type)}}}]->(to_record) "
            "RETURN rel"
        ),
    )


def graph_entity_context(conn, entity_id: str) -> dict[str, list[str]]:
    document_ids = _fetch_cypher_values(
        conn,
        (
            f"MATCH (:Entity {{id: {_cypher_literal(entity_id)}}})-[:HAS_DOCUMENT]->(d:Document) "
            "RETURN d.id AS document_id"
        ),
        "document_id",
    )
    record_ids = _fetch_cypher_values(
        conn,
        (
            f"MATCH (:Entity {{id: {_cypher_literal(entity_id)}}})-[:HAS_RECORD]->(r:Record) "
            "RETURN r.id AS record_id"
        ),
        "record_id",
    )
    linked_record_ids = _fetch_cypher_values(
        conn,
        (
            f"MATCH (:Entity {{id: {_cypher_literal(entity_id)}}})-[:HAS_RECORD]->(r:Record) "
            "OPTIONAL MATCH (r)-[:LINKED_TO*1..2]-(linked:Record) "
            "RETURN linked.id AS linked_record_id"
        ),
        "linked_record_id",
    )
    return {
        "document_ids": sorted(set(document_ids)),
        "record_ids": sorted(set(record_ids + linked_record_ids)),
    }


def ensure_schema() -> None:
    schema_path = Path(__file__).resolve().parents[2] / "spine_schema.sql"
    sql = schema_path.read_text(encoding="utf-8").replace("{{EMBEDDING_DIM}}", str(EMBEDDING_DIM))
    with get_connection() as conn:
        conn.execute(sql)
        conn.commit()
        ensure_age_graph(conn)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
