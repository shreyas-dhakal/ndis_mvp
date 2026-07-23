from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.ai.config import DEFAULT_AGENT_TARGET
from src.ai.runtime import chat_completion

T = TypeVar("T", bound=BaseModel)


def _extract_json_object(content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise RuntimeError("Model returned an empty response")

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
        raise RuntimeError(f"Could not find JSON object in model response: {text}")
    return text[start : end + 1]


def _chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_AGENT_TARGET.model,
    provider: str = DEFAULT_AGENT_TARGET.provider,
    deployment: str | None = DEFAULT_AGENT_TARGET.deployment,
) -> str:
    return chat_completion(
        messages,
        model=model,
        provider=provider,
        deployment=deployment,
    )


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
        model=DEFAULT_AGENT_TARGET.model,
        provider=DEFAULT_AGENT_TARGET.provider,
        deployment=DEFAULT_AGENT_TARGET.deployment,
    )

    try:
        payload = json.loads(_extract_json_object(response))
        return model_cls.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(
            f"Invalid structured response from model: {response}"
        ) from exc
