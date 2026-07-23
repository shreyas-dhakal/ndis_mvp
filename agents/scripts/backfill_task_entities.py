"""One-off backfill: resolve entity_id for existing incident/task records.

records.entity_id already exists on the schema (spine_schema.sql) and is set
automatically for new flagged tasks — classiferAgent.create_task() copies
entity_id from the source record it was triggered from. This script only
fixes historical rows where that copy produced NULL (either the source
record itself had no entity resolved at ingestion time, or the row predates
that copy logic).

For each task with entity_id IS NULL:
  1. Prefer the entity_id already resolved on the record it was triggered_by
     (in case the source record has since been linked to an entity).
  2. Otherwise, run the same heuristic/LLM entity extraction used during
     document ingestion (src.rag.service) against the task's title/content.

Run from the `agents/` directory:
    uv run python scripts/backfill_task_entities.py
"""

from __future__ import annotations

from psycopg.rows import dict_row

from src.rag.db import get_connection, sync_entity_node, sync_entity_record_edge
from src.rag.service import (
    _dedupe_aliases,
    _ensure_entity,
    _heuristic_entity_from_text,
    _llm_entity_from_text,
)


def _resolve_entity_for_task(cur, *, title: str | None, content: str | None) -> dict | None:
    text = "\n".join(part for part in [title, content] if part).strip()
    if not text:
        return None

    extracted = _heuristic_entity_from_text(text=text) or _llm_entity_from_text(text=text)
    if not extracted or not extracted.entity_name:
        return None

    aliases = [
        alias
        for alias in _dedupe_aliases(extracted.aliases)
        if alias.lower() != extracted.entity_name.lower()
    ]
    return _ensure_entity(
        cur,
        entity_name=extracted.entity_name,
        entity_type=extracted.entity_type,
        entity_aliases=", ".join(aliases) or None,
    )


def backfill_task_entities() -> None:
    resolved_from_source = 0
    resolved_from_text = 0
    unresolved = 0

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT r.id, r.title, r.content, l.to_record_id AS source_record_id
                FROM records r
                JOIN links l ON l.from_record_id = r.id AND l.link_type = 'triggered_by'
                WHERE r.record_type = 'incident' AND r.entity_id IS NULL
                """
            )
            tasks = cur.fetchall()

            for task in tasks:
                entity_row = None

                if task["source_record_id"]:
                    cur.execute(
                        "SELECT entity_id FROM records WHERE id = %s",
                        [task["source_record_id"]],
                    )
                    source = cur.fetchone()
                    if source and source["entity_id"]:
                        cur.execute(
                            "SELECT id, entity_type, display_name, aliases FROM entities WHERE id = %s",
                            [source["entity_id"]],
                        )
                        entity_row = cur.fetchone()
                        if entity_row:
                            resolved_from_source += 1

                if entity_row is None:
                    entity_row = _resolve_entity_for_task(
                        cur, title=task["title"], content=task["content"]
                    )
                    if entity_row:
                        resolved_from_text += 1

                if entity_row is None:
                    unresolved += 1
                    continue

                entity_id = str(entity_row["id"])
                cur.execute(
                    "UPDATE records SET entity_id = %s WHERE id = %s",
                    [entity_id, task["id"]],
                )
                cur.execute(
                    """
                    INSERT INTO entity_records (entity_id, record_id, relation_type)
                    VALUES (%s, %s, 'about')
                    ON CONFLICT (entity_id, record_id, relation_type) DO NOTHING
                    """,
                    [entity_id, task["id"]],
                )
                sync_entity_node(
                    conn,
                    entity_id=entity_id,
                    entity_type=entity_row["entity_type"],
                    display_name=entity_row["display_name"],
                )
                sync_entity_record_edge(
                    conn,
                    entity_id=entity_id,
                    record_id=str(task["id"]),
                    relation_type="about",
                )

            conn.commit()

    print(
        f"Backfill complete: {resolved_from_source} resolved from source record, "
        f"{resolved_from_text} resolved from task text, {unresolved} left unresolved "
        "(no entity could be determined)."
    )


if __name__ == "__main__":
    backfill_task_entities()
