from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_optional(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def normalize_provider(provider: str | None, *, default: str) -> str:
    raw = (provider or default).strip().lower().replace("-", "_")
    aliases = {
        "azureopenai": "azure_openai",
        "azure_openai": "azure_openai",
        "fasterwhisper": "faster_whisper",
        "faster_whisper": "faster_whisper",
        "ollama": "ollama",
        "piper": "piper",
    }
    return aliases.get(raw, raw)


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str
    deployment: str | None = None


@dataclass(frozen=True)
class AzureOpenAISettings:
    endpoint: str
    api_key: str
    api_version: str


def _default_embedding_dim(provider: str, model: str) -> int:
    normalized_model = model.strip().lower()
    if normalized_model in {"text-embedding-3-large", "large-embedding-3"}:
        return 3072
    if normalized_model in {"text-embedding-3-small", "small-embedding-3"}:
        return 1536
    if provider == "ollama":
        return 768
    return 1536


OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")

CHAT_PROVIDER = normalize_provider(
    _env_optional("CHAT_PROVIDER", "LLM_PROVIDER"),
    default="azure_openai",
)
DEFAULT_CHAT_MODEL = _env(
    "CHAT_MODEL",
    _env_optional("AZURE_OPENAI_CHAT_MODEL", "OLLAMA_CHAT_MODEL") or "gpt-5.4",
)
CHAT_DEPLOYMENT = _env_optional(
    "CHAT_DEPLOYMENT",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
) or DEFAULT_CHAT_MODEL

AGENT_PROVIDER = normalize_provider(
    _env_optional("AGENT_PROVIDER", "CHAT_PROVIDER", "LLM_PROVIDER"),
    default=CHAT_PROVIDER,
)
AGENT_MODEL = _env(
    "AGENT_MODEL",
    _env_optional(
        "AZURE_OPENAI_AGENT_MODEL",
        "OLLAMA_AGENT_MODEL",
        "CHAT_MODEL",
        "AZURE_OPENAI_CHAT_MODEL",
        "OLLAMA_CHAT_MODEL",
    )
    or DEFAULT_CHAT_MODEL,
)
AGENT_DEPLOYMENT = _env_optional(
    "AGENT_DEPLOYMENT",
    "AZURE_OPENAI_AGENT_DEPLOYMENT",
    "CHAT_DEPLOYMENT",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
) or AGENT_MODEL

EMBEDDING_PROVIDER = normalize_provider(
    _env_optional("EMBEDDING_PROVIDER"),
    default=CHAT_PROVIDER,
)
DEFAULT_EMBEDDING_MODEL = _env(
    "EMBEDDING_MODEL",
    _env_optional("AZURE_OPENAI_EMBEDDING_MODEL", "OLLAMA_EMBED_MODEL")
    or "text-embedding-3-large",
)
EMBEDDING_DEPLOYMENT = _env_optional(
    "EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
) or DEFAULT_EMBEDDING_MODEL

VOICE_PROVIDER = normalize_provider(
    _env_optional("VOICE_PROVIDER", "TRANSCRIPTION_PROVIDER"),
    default="faster_whisper",
)
TRANSCRIPTION_MODEL = _env(
    "TRANSCRIPTION_MODEL",
    _env_optional("AZURE_OPENAI_TRANSCRIPTION_MODEL", "WHISPER_MODEL_SIZE")
    or "small",
)
TRANSCRIPTION_DEPLOYMENT = _env_optional(
    "TRANSCRIPTION_DEPLOYMENT",
    "AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT",
) or TRANSCRIPTION_MODEL
VOICE_TRANSCRIPTION_LANGUAGE = _env_optional("VOICE_TRANSCRIPTION_LANGUAGE")
VOICE_TRANSCRIPTION_TASK = (_env_optional("VOICE_TRANSCRIPTION_TASK") or "translate").lower()
if VOICE_TRANSCRIPTION_TASK not in {"transcribe", "translate"}:
    raise RuntimeError("VOICE_TRANSCRIPTION_TASK must be 'transcribe' or 'translate'")

ENGLISH_OUTPUT_INSTRUCTION = (
    "Always respond in English, regardless of the language used in the input. "
    "Translate internally when necessary and never output non-English text."
)

TTS_PROVIDER = normalize_provider(
    _env_optional("TTS_PROVIDER", "VOICE_PROVIDER"),
    default="piper",
)
TTS_MODEL = _env_optional("TTS_MODEL", "PIPER_MODEL") or "en_US-lessac-medium"
TTS_DEPLOYMENT = _env_optional("TTS_DEPLOYMENT", "AZURE_OPENAI_TTS_DEPLOYMENT") or TTS_MODEL
TTS_VOICE = _env_optional(
    "TTS_VOICE",
    "PIPER_VOICE",
    "AZURE_OPENAI_TTS_VOICE",
    "AZURE_SPEECH_VOICE",
) or TTS_MODEL

EMBED_BATCH_SIZE = _env_int("EMBED_BATCH_SIZE", _env_int("OLLAMA_EMBED_BATCH_SIZE", 32))
EMBED_CONCURRENCY = _env_int(
    "EMBED_CONCURRENCY",
    _env_int("OLLAMA_EMBED_CONCURRENCY", 4),
)
EMBEDDING_DIM = _env_int(
    "EMBEDDING_DIM",
    _default_embedding_dim(EMBEDDING_PROVIDER, DEFAULT_EMBEDDING_MODEL),
)

DEFAULT_CHAT_TARGET = ModelTarget(
    provider=CHAT_PROVIDER,
    model=DEFAULT_CHAT_MODEL,
    deployment=CHAT_DEPLOYMENT,
)
DEFAULT_AGENT_TARGET = ModelTarget(
    provider=AGENT_PROVIDER,
    model=AGENT_MODEL,
    deployment=AGENT_DEPLOYMENT,
)
DEFAULT_EMBEDDING_TARGET = ModelTarget(
    provider=EMBEDDING_PROVIDER,
    model=DEFAULT_EMBEDDING_MODEL,
    deployment=EMBEDDING_DEPLOYMENT,
)
DEFAULT_TRANSCRIPTION_TARGET = ModelTarget(
    provider=VOICE_PROVIDER,
    model=TRANSCRIPTION_MODEL,
    deployment=TRANSCRIPTION_DEPLOYMENT,
)


@lru_cache(maxsize=1)
def get_azure_openai_settings() -> AzureOpenAISettings:
    return AzureOpenAISettings(
        endpoint=_env("AZURE_OPENAI_ENDPOINT").rstrip("/"),
        api_key=_env("AZURE_OPENAI_API_KEY"),
        api_version=_env("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    )
