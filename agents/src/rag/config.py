from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


DATABASE_URL = _env("DATABASE_URL")

OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_CHAT_MODEL = _env("OLLAMA_CHAT_MODEL", "qwen3:8b")

OLLAMA_EMBED_CONCURRENCY = _env_int("OLLAMA_EMBED_CONCURRENCY", 4)
OLLAMA_EMBED_BATCH_SIZE = _env_int("OLLAMA_EMBED_BATCH_SIZE", 32)
EMBEDDING_DIM = _env_int("EMBEDDING_DIM", 768)

DB_POOL_MIN_SIZE = _env_int("DB_POOL_MIN_SIZE", 1)
DB_POOL_MAX_SIZE = _env_int("DB_POOL_MAX_SIZE", 8)

RETRIEVAL_SEMANTIC_CANDIDATES = _env_int("RETRIEVAL_SEMANTIC_CANDIDATES", 60)
RETRIEVAL_LEXICAL_CANDIDATES = _env_int("RETRIEVAL_LEXICAL_CANDIDATES", 60)
RETRIEVAL_RRF_K = _env_int("RETRIEVAL_RRF_K", 50)
