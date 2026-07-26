from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from .config import (
    DEFAULT_CHAT_TARGET,
    DEFAULT_EMBEDDING_TARGET,
    DEFAULT_TRANSCRIPTION_TARGET,
    ENGLISH_OUTPUT_INSTRUCTION,
    EMBED_BATCH_SIZE,
    EMBED_CONCURRENCY,
    EMBEDDING_DIM,
    OLLAMA_BASE_URL,
    VOICE_TRANSCRIPTION_LANGUAGE,
    VOICE_TRANSCRIPTION_TASK,
    ModelTarget,
    get_azure_openai_settings,
    normalize_provider,
)

_TIMEOUT_SECONDS = 120


class EmbeddingUnavailable(RuntimeError):
    pass


def _resolve_target(
    *,
    default: ModelTarget,
    provider: str | None = None,
    model: str | None = None,
    deployment: str | None = None,
) -> ModelTarget:
    resolved_provider = normalize_provider(provider, default=default.provider)
    resolved_model = (model or default.model).strip()
    resolved_deployment = (deployment or default.deployment or resolved_model).strip()
    return ModelTarget(
        provider=resolved_provider,
        model=resolved_model,
        deployment=resolved_deployment,
    )


@lru_cache(maxsize=1)
def _sync_client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT_SECONDS,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def _azure_headers() -> dict[str, str]:
    settings = get_azure_openai_settings()
    return {"api-key": settings.api_key}


def _azure_url(*, deployment: str, path: str) -> str:
    settings = get_azure_openai_settings()
    return (
        f"{settings.endpoint}/openai/deployments/{deployment}/{path}"
        f"?api-version={settings.api_version}"
    )


def _extract_chat_content(payload: object) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Chat service returned a non-object response")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Chat service returned no choices")

    message = (choices[0] or {}).get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Chat service returned a malformed message payload")

    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
        if out:
            return "\n".join(out)

    raise RuntimeError("Chat service returned an unexpected response")


def _validate_embedding(values: list[float], *, label: str) -> list[float]:
    if len(values) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding dimension mismatch for {label}: expected {EMBEDDING_DIM}, got {len(values)}"
        )
    return values


def _parse_ollama_embeddings(payload: object, *, label: str) -> list[list[float]]:
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


def _parse_azure_embeddings(payload: object, *, label: str) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Embedding service returned a non-object response")

    rows = payload.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("Embedding service response did not include data")

    indexed_rows: list[tuple[int, list[float]]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("embedding"), list):
            raise RuntimeError("Embedding service returned malformed embedding data")
        embedding = _validate_embedding(
            [float(value) for value in row["embedding"]],
            label=f"{label}[{index}]",
        )
        indexed_rows.append((int(row.get("index", index)), embedding))

    indexed_rows.sort(key=lambda item: item[0])
    return [embedding for _, embedding in indexed_rows]


def _ollama_embed_payload(model: str, texts: str | list[str]) -> dict[str, object]:
    return {"model": model, "input": texts, "keep_alive": "10m"}


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    provider: str | None = None,
    deployment: str | None = None,
    temperature: float | None = None,
) -> str:
    messages = [message.copy() for message in messages]
    system_message = next(
        (message for message in messages if message.get("role") == "system"),
        None,
    )
    if system_message is None:
        messages.insert(0, {"role": "system", "content": ENGLISH_OUTPUT_INSTRUCTION})
    else:
        system_message["content"] = (
            f"{system_message.get('content', '').strip()}\n\n"
            f"{ENGLISH_OUTPUT_INSTRUCTION}"
        ).strip()
    target = _resolve_target(
        default=DEFAULT_CHAT_TARGET,
        provider=provider,
        model=model,
        deployment=deployment,
    )

    if target.provider == "ollama":
        payload: dict[str, object] = {
            "model": target.model,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            payload["options"] = {"temperature": float(temperature)}
        try:
            response = _sync_client().post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
                json=payload,
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

    if target.provider == "azure_openai":
        payload: dict[str, object] = {"messages": messages}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        try:
            response = _sync_client().post(
                _azure_url(deployment=target.deployment or target.model, path="chat/completions"),
                headers=_azure_headers(),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Chat service unavailable at Azure OpenAI") from exc
        return _extract_chat_content(response.json())

    raise RuntimeError(f"Unsupported chat provider: {target.provider}")


@lru_cache(maxsize=256)
def embed_query(
    text: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    deployment: str | None = None,
) -> list[float]:
    target = _resolve_target(
        default=DEFAULT_EMBEDDING_TARGET,
        provider=provider,
        model=model,
        deployment=deployment,
    )
    client = _sync_client()

    if target.provider == "ollama":
        base_url = OLLAMA_BASE_URL.rstrip("/")
        try:
            response = client.post(
                f"{base_url}/api/embed",
                json=_ollama_embed_payload(target.model, text),
            )
            if response.status_code == 200:
                embeddings = _parse_ollama_embeddings(response.json(), label="query")
                return embeddings[0]

            fallback = client.post(
                f"{base_url}/api/embeddings",
                json={"model": target.model, "prompt": text, "keep_alive": "10m"},
            )
            if fallback.status_code != 200:
                raise EmbeddingUnavailable(fallback.text)
            embeddings = _parse_ollama_embeddings(fallback.json(), label="query")
            return embeddings[0]
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailable(f"Embedding service unavailable at {OLLAMA_BASE_URL}") from exc

    if target.provider == "azure_openai":
        try:
            response = client.post(
                _azure_url(deployment=target.deployment or target.model, path="embeddings"),
                headers=_azure_headers(),
                json={"input": text},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailable("Embedding service unavailable at Azure OpenAI") from exc
        embeddings = _parse_azure_embeddings(response.json(), label="query")
        return embeddings[0]

    raise EmbeddingUnavailable(f"Unsupported embedding provider: {target.provider}")


async def _embed_batch_ollama(
    client: httpx.AsyncClient,
    texts: list[str],
    *,
    target: ModelTarget,
) -> list[list[float]]:
    response = await client.post(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/embed",
        json=_ollama_embed_payload(target.model, texts),
    )
    if response.status_code == 200:
        return _parse_ollama_embeddings(response.json(), label="batch")

    semaphore = asyncio.Semaphore(max(1, EMBED_CONCURRENCY))

    async def embed_one(text: str) -> list[float]:
        async with semaphore:
            fallback = await client.post(
                f"{OLLAMA_BASE_URL.rstrip('/')}/api/embeddings",
                json={"model": target.model, "prompt": text, "keep_alive": "10m"},
            )
            if fallback.status_code != 200:
                raise EmbeddingUnavailable(fallback.text)
            return _parse_ollama_embeddings(fallback.json(), label="legacy")[0]

    return list(await asyncio.gather(*(embed_one(text) for text in texts)))


async def _embed_batch_azure(
    client: httpx.AsyncClient,
    texts: list[str],
    *,
    target: ModelTarget,
) -> list[list[float]]:
    response = await client.post(
        _azure_url(deployment=target.deployment or target.model, path="embeddings"),
        headers=_azure_headers(),
        json={"input": texts},
    )
    response.raise_for_status()
    return _parse_azure_embeddings(response.json(), label="batch")


async def embed_texts_async(
    texts: list[str],
    *,
    model: str | None = None,
    provider: str | None = None,
    deployment: str | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    target = _resolve_target(
        default=DEFAULT_EMBEDDING_TARGET,
        provider=provider,
        model=model,
        deployment=deployment,
    )

    limits = httpx.Limits(
        max_connections=max(1, EMBED_CONCURRENCY),
        max_keepalive_connections=max(1, EMBED_CONCURRENCY),
    )
    batch_size = max(1, EMBED_BATCH_SIZE)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, limits=limits) as client:
            out: list[list[float]] = []
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                if target.provider == "ollama":
                    out.extend(await _embed_batch_ollama(client, batch, target=target))
                elif target.provider == "azure_openai":
                    out.extend(await _embed_batch_azure(client, batch, target=target))
                else:
                    raise EmbeddingUnavailable(
                        f"Unsupported embedding provider: {target.provider}"
                    )
            return out
    except httpx.HTTPError as exc:
        if target.provider == "ollama":
            raise EmbeddingUnavailable(
                f"Embedding service unavailable at {OLLAMA_BASE_URL}"
            ) from exc
        raise EmbeddingUnavailable("Embedding service unavailable at Azure OpenAI") from exc


def _format_timestamp(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def transcribe_audio_file(
    audio_path: str,
    *,
    model: str | None = None,
    provider: str | None = None,
    deployment: str | None = None,
    language: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    target = _resolve_target(
        default=DEFAULT_TRANSCRIPTION_TARGET,
        provider=provider,
        model=model,
        deployment=deployment,
    )

    if target.provider == "faster_whisper":
        from faster_whisper import WhisperModel

        whisper_model = WhisperModel(
            target.model,
            device="cpu",
            compute_type="int8",
        )
        whisper_kwargs: dict[str, Any] = {
            "task": VOICE_TRANSCRIPTION_TASK,
            "vad_filter": True,
        }
        if language or VOICE_TRANSCRIPTION_LANGUAGE:
            whisper_kwargs["language"] = language or VOICE_TRANSCRIPTION_LANGUAGE
        segments, _info = whisper_model.transcribe(audio_path, **whisper_kwargs)
        lines = [
            {
                "speaker": "SPEAKER_00",
                "start": float(segment.start),
                "text": (segment.text or "").strip(),
            }
            for segment in segments
            if (segment.text or "").strip()
        ]
        transcript_text = "\n".join(
            f"[{_format_timestamp(line['start'])}] {line['speaker']}: {line['text']}"
            for line in lines
        )
        return transcript_text, lines

    if target.provider == "azure_openai":
        try:
            with Path(audio_path).open("rb") as audio_file:
                response = _sync_client().post(
                    _azure_url(
                        deployment=target.deployment or target.model,
                        path=(
                            "audio/translations"
                            if VOICE_TRANSCRIPTION_TASK == "translate"
                            else "audio/transcriptions"
                        ),
                    ),
                    headers=_azure_headers(),
                    data={
                        "model": target.model,
                        "response_format": "json",
                        **(
                            {"language": language or VOICE_TRANSCRIPTION_LANGUAGE}
                            if VOICE_TRANSCRIPTION_TASK == "transcribe"
                            and (language or VOICE_TRANSCRIPTION_LANGUAGE)
                            else {}
                        ),
                    },
                    files={
                        "file": (
                            Path(audio_path).name,
                            audio_file,
                            "application/octet-stream",
                        )
                    },
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Transcription service unavailable at Azure OpenAI") from exc

        payload = response.json()
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Transcription service returned an unexpected response")
        cleaned = text.strip()
        lines = [{"speaker": "SPEAKER_00", "start": 0.0, "text": cleaned}]
        transcript_text = f"[00:00:00] SPEAKER_00: {cleaned}"
        return transcript_text, lines

    raise RuntimeError(f"Unsupported transcription provider: {target.provider}")
