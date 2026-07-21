from __future__ import annotations

import json
import os
from typing import TypeVar

import httpx
from dotenv import load_dotenv

from pydantic import BaseModel, ValidationError

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen3:8b")

MODEL_NAME = os.getenv("OLLAMA_AGENT_MODEL") or os.getenv(
    "OLLAMA_CHAT_MODEL", "qwen3:8b"
)
_TIMEOUT_SECONDS = 120

T = TypeVar("T", bound=BaseModel)


def _extract_json_object(content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty response")

    if text.startswith("```"):
        for part in text.split("```"):
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{") and cleaned.endswith("}"):
                return cleaned

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(f"Could not find JSON object in Ollama response: {text}")
    return text[start : end + 1]


def _chat_completion(
    messages: list[dict[str, str]], *, model: str = OLLAMA_CHAT_MODEL
) -> str:
    payload: dict[str, object] = {"model": model, "messages": messages, "stream": False}

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json=payload,
            timeout=_TIMEOUT_SECONDS,
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


def invoke_structured(model_cls: type[T], *, system_prompt: str, user_prompt: str) -> T:
    schema = json.dumps(model_cls.model_json_schema(), indent=2)
    response = _chat_completion(
        [
            {
                "role": "system",
                "content": (
                    f"{system_prompt.strip()}\n\n"
                    "Return only valid JSON. Do not include markdown fences, commentary, or extra text. "
                    f"The JSON must match this schema exactly:\n{schema}"
                ),
            },
            {"role": "user", "content": user_prompt.strip()},
        ],
        model=MODEL_NAME,
    )

    try:
        payload = json.loads(_extract_json_object(response))
        return model_cls.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(
            f"Invalid structured response from Ollama: {response}"
        ) from exc
