from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

from .config import (
    EMBEDDING_DIM,
    OLLAMA_BASE_URL,
    OLLAMA_CHAT_MODEL,
    OLLAMA_EMBED_BATCH_SIZE,
    OLLAMA_EMBED_CONCURRENCY,
    OLLAMA_EMBED_MODEL,
)

_TIMEOUT_SECONDS = 120


class EmbeddingUnavailable(RuntimeError):
    pass


def _validate_embedding(values: list[float], *, label: str) -> list[float]:
    if len(values) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch for {label}: expected {EMBEDDING_DIM}, got {len(values)}"
        )
    return values


def _parse_embeddings(payload: object, *, label: str) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Embedding service returned a non-object response")
    raw = payload.get("embeddings")
    if isinstance(raw, list):
        embeddings = raw
    elif isinstance(payload.get("embedding"), list):
        embeddings = [payload["embedding"]]
    else:
        raise RuntimeError("Embedding service response did not include embeddings")

    out: list[list[float]] = []
    for index, embedding in enumerate(embeddings):
        if not isinstance(embedding, list):
            raise RuntimeError("Embedding service returned malformed embedding data")
        out.append(_validate_embedding([float(value) for value in embedding], label=f"{label}[{index}]"))
    return out


def _embed_payload(model: str, texts: str | list[str]) -> dict[str, object]:
    return {"model": model, "input": texts, "keep_alive": "10m"}


@lru_cache(maxsize=1)
def _sync_client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT_SECONDS,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


@lru_cache(maxsize=256)
def embed_query(text: str, *, model: str = OLLAMA_EMBED_MODEL) -> list[float]:
    client = _sync_client()
    base_url = OLLAMA_BASE_URL.rstrip("/")
    try:
        response = client.post(f"{base_url}/api/embed", json=_embed_payload(model, text))
        if response.status_code == 200:
            embeddings = _parse_embeddings(response.json(), label="query")
            return embeddings[0]

        fallback = client.post(
            f"{base_url}/api/embeddings",
            json={"model": model, "prompt": text, "keep_alive": "10m"},
        )
        if fallback.status_code != 200:
            raise EmbeddingUnavailable(fallback.text)
        embeddings = _parse_embeddings(fallback.json(), label="query")
        return embeddings[0]
    except httpx.HTTPError as exc:
        raise EmbeddingUnavailable(f"Embedding service unavailable at {OLLAMA_BASE_URL}") from exc


async def _embed_batch(client: httpx.AsyncClient, texts: list[str], *, model: str) -> list[list[float]]:
    response = await client.post(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/embed",
        json=_embed_payload(model, texts),
    )
    if response.status_code == 200:
        return _parse_embeddings(response.json(), label="batch")

    semaphore = asyncio.Semaphore(max(1, OLLAMA_EMBED_CONCURRENCY))

    async def embed_one(text: str) -> list[float]:
        async with semaphore:
            fallback = await client.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/embeddings",
                json={"model": model, "prompt": text, "keep_alive": "10m"},
            )
            if fallback.status_code != 200:
                raise EmbeddingUnavailable(fallback.text)
            return _parse_embeddings(fallback.json(), label="legacy")[0]

    return list(await asyncio.gather(*(embed_one(text) for text in texts)))


async def embed_texts_async(texts: list[str], *, model: str = OLLAMA_EMBED_MODEL) -> list[list[float]]:
    if not texts:
        return []

    batch_size = max(1, OLLAMA_EMBED_BATCH_SIZE)
    limits = httpx.Limits(
        max_connections=max(1, OLLAMA_EMBED_CONCURRENCY),
        max_keepalive_connections=max(1, OLLAMA_EMBED_CONCURRENCY),
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, limits=limits) as client:
            out: list[list[float]] = []
            for start in range(0, len(texts), batch_size):
                out.extend(await _embed_batch(client, texts[start : start + batch_size], model=model))
            return out
    except httpx.HTTPError as exc:
        raise EmbeddingUnavailable(f"Embedding service unavailable at {OLLAMA_BASE_URL}") from exc


def chat_completion(messages: list[dict[str, str]], *, model: str = OLLAMA_CHAT_MODEL) -> str:
    try:
        response = _sync_client().post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Chat service unavailable at {OLLAMA_BASE_URL}") from exc

    payload = response.json()
    message = payload.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Chat service returned an unexpected response")
    return content.strip()
