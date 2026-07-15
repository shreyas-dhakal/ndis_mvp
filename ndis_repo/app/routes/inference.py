from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.inference.ollama_client import ollama_chat_completions
from app.inference.openai_compat import openai_chat_response
from app.inference.registry import resolve_provider_for_model

router = APIRouter(prefix="/v1", tags=["inference"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionsRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    stream: bool = False

    # OpenAI supports many other fields; we ignore for now.


@router.get("/models")
def list_models() -> dict[str, Any]:
    # Minimal list for OpenAI-compat clients.
    # We resolve at request time from the registry.
    return {"object": "list", "data": [{"id": "*"}]}


@router.post("/chat/completions")
def chat_completions(req: ChatCompletionsRequest) -> dict[str, Any]:
    if req.stream:
        # Not implemented for now.
        return openai_chat_response(model=req.model, content="Streaming not implemented")

    provider = resolve_provider_for_model(req.model)
    if provider.provider == "ollama":
        # Ollama expects messages objects; we pass through role/content.
        content = ollama_chat_completions(
            model=provider.model_id,
            messages=[m.model_dump() for m in req.messages],
            temperature=req.temperature,
        )
    else:
        raise RuntimeError(f"Unsupported provider: {provider.provider}")

    return openai_chat_response(model=req.model, content=content)
