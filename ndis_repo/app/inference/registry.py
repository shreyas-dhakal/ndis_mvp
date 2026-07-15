from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from app.core.config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL


@dataclass(frozen=True)
class ModelProvider:
    provider: str  # e.g. "ollama"
    model_id: str  # provider-specific model name


def __registry() -> dict[str, ModelProvider]:
    # : expose the configured Ollama chat model under its own name.
    return {
        OLLAMA_CHAT_MODEL: ModelProvider(provider="ollama", model_id=OLLAMA_CHAT_MODEL),
    }


def load_model_registry() -> dict[str, ModelProvider]:
    """Load a config-driven model registry.

    Env:
      INFERENCE_MODEL_REGISTRY_JSON: JSON object mapping "public model name" -> provider config

    Example:
    {
      "qwen3:8b": {"provider": "ollama", "model_id": "qwen3:8b"},
      "my-qwen": {"provider": "ollama", "model_id": "qwen3:8b"}
    }
    """

    raw = os.getenv("INFERENCE_MODEL_REGISTRY_JSON")
    if not raw:
        return __registry()

    parsed = json.loads(raw)
    registry: dict[str, ModelProvider] = {}
    for public_name, cfg in parsed.items():
        provider = (cfg or {}).get("provider")
        model_id = (cfg or {}).get("model_id")
        if not provider or not model_id:
            continue
        registry[str(public_name)] = ModelProvider(
            provider=provider, model_id=str(model_id)
        )
    return registry or __registry()


def resolve_provider_for_model(model: str) -> ModelProvider:
    registry = load_model_registry()
    if model in registry:
        return registry[model]

    # Fallback: if the model name matches the configured Ollama chat model.
    if model == OLLAMA_CHAT_MODEL:
        return ModelProvider(provider="ollama", model_id=OLLAMA_CHAT_MODEL)

    # Last resort: if registry is non-empty, pick the first.
    if registry:
        return next(iter(registry.values()))

    raise RuntimeError(f"No inference model provider found for model={model}")
