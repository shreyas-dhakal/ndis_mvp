from __future__ import annotations

import asyncio
from functools import lru_cache
import logging

import httpx
from fastapi import HTTPException

from app.core.config import (
    EMBEDDING_DIM,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_BATCH_SIZE,
    OLLAMA_EMBED_CONCURRENCY,
    OLLAMA_EMBED_MODEL,
)


logger = logging.getLogger("app")
_EMBED_TIMEOUT_SECONDS = 120


class _BatchEndpointUnavailable(RuntimeError):
    pass


def _validate_embedding(embedding: list[float], *, text_label: str) -> list[float]:
    if len(embedding) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch for {text_label}: "
            f"expected {EMBEDDING_DIM}, got {len(embedding)}"
        )
    return embedding


def _parse_embedding_response(data: object, *, text_label: str) -> list[list[float]]:
    if not isinstance(data, dict):
        raise RuntimeError("Embedding service returned a non-object response")

    if isinstance(data.get("embeddings"), list):
        embeddings = data["embeddings"]
    elif isinstance(data.get("embedding"), list):
        embeddings = [data["embedding"]]
    else:
        raise RuntimeError("Embedding service response did not include embeddings")

    parsed: list[list[float]] = []
    for idx, embedding in enumerate(embeddings):
        if not isinstance(embedding, list):
            raise RuntimeError("Embedding service returned a malformed embedding payload")
        parsed.append(
            _validate_embedding(
                [float(value) for value in embedding],
                text_label=f"{text_label}[{idx}]",
            )
        )
    return parsed


def _embed_payload(*, model: str, texts: list[str] | str) -> dict[str, object]:
    return {
        "model": model,
        "input": texts,
        # Keep the model warm for repeated retrieval queries and ingestion batches.
        "keep_alive": "10m",
    }


@lru_cache(maxsize=1)
def sync_client() -> httpx.Client:
    return httpx.Client(
        timeout=_EMBED_TIMEOUT_SECONDS,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


@lru_cache(maxsize=256)
def embed_query(text: str, *, model: str = OLLAMA_EMBED_MODEL) -> list[float]:
    base_url = OLLAMA_BASE_URL.rstrip("/")
    client = sync_client()
    try:
        resp = client.post(
            f"{base_url}/api/embed",
            json=_embed_payload(model=model, texts=text),
        )
        if resp.status_code == 200:
            embeddings = _parse_embedding_response(
                resp.json(),
                text_label="query",
            )
            if len(embeddings) != 1:
                raise RuntimeError("Expected a single embedding for query text")
            return embeddings[0]

        fallback = client.post(
            f"{base_url}/api/embeddings",
            json={"model": model, "prompt": text, "keep_alive": "10m"},
        )
        if fallback.status_code != 200:
            raise RuntimeError(f"Ollama embeddings error: {fallback.text}")
        embeddings = _parse_embedding_response(fallback.json(), text_label="query")
        if len(embeddings) != 1:
            raise RuntimeError("Expected a single embedding for query text")
        return embeddings[0]
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Embedding service unavailable at {OLLAMA_BASE_URL}",
        ) from exc


async def _embed_batch_request(
    client: httpx.AsyncClient,
    *,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    resp = await client.post(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/embed",
        json=_embed_payload(model=model, texts=texts),
    )
    if resp.status_code != 200:
        raise _BatchEndpointUnavailable(resp.text)
    embeddings = _parse_embedding_response(
        resp.json(),
        text_label="batch",
    )
    if len(embeddings) != len(texts):
        raise RuntimeError(
            f"Embedding batch size mismatch: expected {len(texts)}, got {len(embeddings)}"
        )
    return embeddings


async def _embed_legacy_request(
    client: httpx.AsyncClient,
    *,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    semaphore = asyncio.Semaphore(max(1, OLLAMA_EMBED_CONCURRENCY))

    async def embed_one(text: str) -> list[float]:
        async with semaphore:
            resp = await client.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/embeddings",
                json={"model": model, "prompt": text, "keep_alive": "10m"},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama embeddings error: {resp.text}")
            embeddings = _parse_embedding_response(resp.json(), text_label="legacy")
            if len(embeddings) != 1:
                raise RuntimeError("Expected a single embedding from legacy endpoint")
            return embeddings[0]

    return list(await asyncio.gather(*(embed_one(text) for text in texts)))


async def embed_texts_async(
    texts: list[str],
    *,
    model: str = OLLAMA_EMBED_MODEL,
) -> list[list[float]]:
    if not texts:
        return []

    batch_size = max(1, OLLAMA_EMBED_BATCH_SIZE)
    limits = httpx.Limits(
        max_connections=max(1, OLLAMA_EMBED_CONCURRENCY),
        max_keepalive_connections=max(1, OLLAMA_EMBED_CONCURRENCY),
    )

    async with httpx.AsyncClient(timeout=_EMBED_TIMEOUT_SECONDS, limits=limits) as client:
        try:
            embedded: list[list[float]] = []
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                embedded.extend(
                    await _embed_batch_request(client, model=model, texts=batch)
                )
            return embedded
        except _BatchEndpointUnavailable:
            logger.info(
                "Falling back to legacy Ollama /api/embeddings endpoint for ingestion"
            )
            return await _embed_legacy_request(client, model=model, texts=texts)
