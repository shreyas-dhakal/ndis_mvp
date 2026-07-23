from src.ai.config import DEFAULT_CHAT_MODEL
from .db import close_pool, ensure_schema, get_connection, get_pool
from .embeddings import chat_completion
from .service import (
    answer_question,
    delete_document,
    ingest_upload,
    find_entity_candidates,
    list_documents,
    retrieve_chunks,
    store_generated_note,
)

__all__ = [
    "answer_question",
    "chat_completion",
    "close_pool",
    "delete_document",
    "ensure_schema",
    "get_connection",
    "get_pool",
    "ingest_upload",
    "find_entity_candidates",
    "list_documents",
    "DEFAULT_CHAT_MODEL",
    "retrieve_chunks",
    "store_generated_note",
]
