from __future__ import annotations

import os
from typing import Any, Callable, TypeVar


T = TypeVar("T", bound=Callable[..., Any])


def _truthy_env(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "t", "yes", "y"}


LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT")

# LangSmith's `traceable` decorator requires this env var.
if LANGSMITH_API_KEY and not _truthy_env("LANGSMITH_TRACING_V2"):
    os.environ["LANGSMITH_TRACING_V2"] = "true"


def langsmith_enabled() -> bool:
    return bool(LANGSMITH_API_KEY) and _truthy_env("LANGSMITH_TRACING_V2")


def maybe_traceable(
    *,
    name: str,
    run_type: str,
    process_inputs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    process_outputs: Callable[[Any], Any] | None = None,
) -> Callable[[T], T]:
    if not langsmith_enabled():
        def _identity(fn: T) -> T:
            return fn

        return _identity

    try:
        from langsmith.run_helpers import traceable
    except Exception:
        # If langsmith isn't installed, we keep behavior unchanged.
        def _identity(fn: T) -> T:
            return fn

        return _identity

    kwargs: dict[str, Any] = {
        "name": name,
        "run_type": run_type,
        "project_name": LANGSMITH_PROJECT,
    }
    if process_inputs is not None:
        kwargs["process_inputs"] = process_inputs
    if process_outputs is not None:
        kwargs["process_outputs"] = process_outputs

    def _decorator(fn: T) -> T:
        return traceable(**kwargs)(fn)

    return _decorator


def _truncate(s: str, *, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "…"


def process_ollama_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    # Avoid sending huge context blobs. Keep enough info to debug quality.
    model = inputs.get("model")
    messages = inputs.get("messages")
    if isinstance(messages, list):
        compact: list[dict[str, Any]] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if isinstance(content, str):
                content = _truncate(content, limit=1200)
            compact.append({"role": role, "content": content})
        inputs = {**inputs, "model": model, "messages": compact}
    return inputs


def process_ollama_outputs(outputs: Any) -> Any:
    if isinstance(outputs, str):
        return _truncate(outputs, limit=4000)
    return outputs
