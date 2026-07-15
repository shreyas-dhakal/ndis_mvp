from __future__ import annotations

from typing import Any

import httpx

from app.core.config import OLLAMA_BASE_URL
from app.core.langsmith_tracing import maybe_traceable, process_ollama_inputs, process_ollama_outputs


@maybe_traceable(
    name="ollama_chat_completions",
    run_type="llm",
    process_inputs=process_ollama_inputs,
    process_outputs=process_ollama_outputs,
)


def ollama_chat_completions(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    num_predict: int | None = None,
) -> str:
    """Minimal wrapper for Ollama chat completions.

    Uses Ollama's /api/chat endpoint and returns assistant content.
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if num_predict is not None:
        options["num_predict"] = int(num_predict)
    if options:
        payload["options"] = options

    with httpx.Client(timeout=180) as client:
        resp = client.post(url, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Ollama chat error ({resp.status_code}): {resp.text}")
        data = resp.json()

    msg = (data or {}).get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    # Some Ollama versions/models may return alternative shapes.
    # OpenAI-compat-like "choices" is handled as a best-effort fallback.
    choices = (data or {}).get("choices")
    if isinstance(choices, list) and choices:
        choice0 = choices[0] or {}
        msg0 = choice0.get("message") or {}
        c2 = msg0.get("content")
        if isinstance(c2, str) and c2.strip():
            return c2.strip()

    for k in ("response", "content", "text"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # Include the returned payload to make debugging possible.
    # Keep it bounded to avoid spamming logs with huge responses.
    data_repr = repr(data)
    if len(data_repr) > 2000:
        data_repr = data_repr[:2000] + "…(truncated)"
    raise RuntimeError(f"Ollama chat returned no content. Response={data_repr}")
