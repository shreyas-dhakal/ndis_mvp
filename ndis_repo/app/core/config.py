from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


POSTGRES_USER = _env("POSTGRES_USER", "rag")
POSTGRES_PASSWORD = _env("POSTGRES_PASSWORD", "rag")
POSTGRES_HOST = _env("POSTGRES_HOST", "localhost")
POSTGRES_PORT = _env("POSTGRES_PORT", "5432")
POSTGRES_DB = _env("POSTGRES_DB", "rag")

DATABASE_URL = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

PSYCOPG_DSN = (
    f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
    f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
)

OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_CHAT_MODEL = _env("OLLAMA_CHAT_MODEL", "qwen3:8b")
OLLAMA_EMBED_CONCURRENCY = _env_int("OLLAMA_EMBED_CONCURRENCY", 6)
OLLAMA_EMBED_BATCH_SIZE = _env_int("OLLAMA_EMBED_BATCH_SIZE", 64)
EMBEDDING_DIM = _env_int("EMBEDDING_DIM", 768)

DB_POOL_MIN_SIZE = _env_int("DB_POOL_MIN_SIZE", 1)
DB_POOL_MAX_SIZE = _env_int("DB_POOL_MAX_SIZE", 10)

RETRIEVAL_SEMANTIC_CANDIDATES = _env_int("RETRIEVAL_SEMANTIC_CANDIDATES", 80)
RETRIEVAL_LEXICAL_CANDIDATES = _env_int("RETRIEVAL_LEXICAL_CANDIDATES", 80)
RETRIEVAL_RRF_K = _env_int("RETRIEVAL_RRF_K", 50)

DATA_DIR = _env("DATA_DIR", "./data")

LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

LOG_DIR = os.getenv("LOG_DIR", "./logs")

# Optional config-driven inference model registry.
# See app/inference/registry.py
INFERENCE_MODEL_REGISTRY_JSON = os.getenv("INFERENCE_MODEL_REGISTRY_JSON")
