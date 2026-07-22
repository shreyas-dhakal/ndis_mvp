from __future__ import annotations

import os

from dotenv import load_dotenv
from src.ai.config import EMBEDDING_DIM

load_dotenv()


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


DATABASE_URL = _env("DATABASE_URL")

DB_POOL_MIN_SIZE = _env_int("DB_POOL_MIN_SIZE", 1)
DB_POOL_MAX_SIZE = _env_int("DB_POOL_MAX_SIZE", 8)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

RETRIEVAL_SEMANTIC_CANDIDATES = _env_int("RETRIEVAL_SEMANTIC_CANDIDATES", 60)
RETRIEVAL_LEXICAL_CANDIDATES = _env_int("RETRIEVAL_LEXICAL_CANDIDATES", 60)
RETRIEVAL_TRIGRAM_CANDIDATES = _env_int("RETRIEVAL_TRIGRAM_CANDIDATES", 40)
RETRIEVAL_RRF_K = _env_int("RETRIEVAL_RRF_K", 50)
RETRIEVAL_GROUP_LIMIT = _env_int("RETRIEVAL_GROUP_LIMIT", 12)
RETRIEVAL_ADJACENT_WINDOW = _env_int("RETRIEVAL_ADJACENT_WINDOW", 1)

AGE_ENABLED = _env_bool("AGE_ENABLED", False)
AGE_GRAPH_NAME = _env("AGE_GRAPH_NAME", "ndis_context")
