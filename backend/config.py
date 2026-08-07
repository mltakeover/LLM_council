"""Configuration for LLM Council using cloud providers and local Ollama models."""

import ipaddress
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


def _csv_values(value: str) -> list[str]:
    """Return unique, non-empty comma-separated values in their original order."""

    return list(
        dict.fromkeys(
            item.strip()
            for item in value.split(",")
            if item.strip()
        )
    )


def _is_configured_api_key(value: str | None) -> bool:
    """Reject missing values and common documentation placeholders."""

    if not value or not value.strip():
        return False

    normalized = value.strip().lower()
    placeholder_values = {
        "redacted",
        "replace-me",
        "replace_me",
        "your-api-key",
    }

    return (
        normalized not in placeholder_values
        and not normalized.startswith("your-")
        and not normalized.startswith("<your-")
    )


def _is_loopback_url(value: str) -> bool:
    """Return True only for explicit localhost or loopback-IP endpoints."""

    hostname = (urlsplit(value).hostname or "").strip().lower()
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


DATA_DIR = os.getenv("DATA_DIR", "data/conversations")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/llm_council.db")
APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1"

MAX_PROMPT_CHARACTERS = int(
    os.getenv("MAX_PROMPT_CHARACTERS", "100000")
)
MAX_COUNCIL_MODELS = int(os.getenv("MAX_COUNCIL_MODELS", "8"))
MAX_CONTEXT_CHARACTERS = int(
    os.getenv("MAX_CONTEXT_CHARACTERS", "60000")
)
MAX_DOCUMENTS_PER_MESSAGE = int(
    os.getenv("MAX_DOCUMENTS_PER_MESSAGE", "5")
)
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(20 * 1024 * 1024)))
DOCUMENT_CHUNK_CHARACTERS = int(
    os.getenv("DOCUMENT_CHUNK_CHARACTERS", "12000")
)
DOCUMENT_CHUNK_OVERLAP = int(
    os.getenv("DOCUMENT_CHUNK_OVERLAP", "500")
)
MAX_DOCUMENT_CHUNKS = int(os.getenv("MAX_DOCUMENT_CHUNKS", "12"))

PROVIDER_MAX_ATTEMPTS = int(
    os.getenv("PROVIDER_MAX_ATTEMPTS", "3")
)
PROVIDER_RETRY_BASE_SECONDS = float(
    os.getenv("PROVIDER_RETRY_BASE_SECONDS", "1")
)
PROVIDER_RETRY_MAX_SECONDS = float(
    os.getenv("PROVIDER_RETRY_MAX_SECONDS", "8")
)
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "300"))
TITLE_TIMEOUT = float(os.getenv("TITLE_TIMEOUT", "90"))
ANTHROPIC_MAX_TOKENS = int(
    os.getenv("ANTHROPIC_MAX_TOKENS", "8192")
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434/v1/",
).strip()
OLLAMA_ENDPOINT_IS_LOCAL = _is_loopback_url(OLLAMA_BASE_URL)

OLLAMA_DISCOVERY_TIMEOUT = float(
    os.getenv("OLLAMA_DISCOVERY_TIMEOUT", "5")
)

OLLAMA_MAX_CONCURRENCY = int(
    os.getenv("OLLAMA_MAX_CONCURRENCY", "1")
)

if OLLAMA_MAX_CONCURRENCY < 1:
    raise RuntimeError("OLLAMA_MAX_CONCURRENCY must be at least 1.")

if not 1 <= MAX_COUNCIL_MODELS <= 26:
    raise RuntimeError("MAX_COUNCIL_MODELS must be between 1 and 26.")

if MAX_PROMPT_CHARACTERS < 1:
    raise RuntimeError("MAX_PROMPT_CHARACTERS must be at least 1.")

if MAX_CONTEXT_CHARACTERS < 0:
    raise RuntimeError("MAX_CONTEXT_CHARACTERS cannot be negative.")

if MAX_DOCUMENTS_PER_MESSAGE < 1:
    raise RuntimeError("MAX_DOCUMENTS_PER_MESSAGE must be at least 1.")

if UPLOAD_MAX_BYTES < 1:
    raise RuntimeError("UPLOAD_MAX_BYTES must be at least 1.")

if DOCUMENT_CHUNK_CHARACTERS < 1000:
    raise RuntimeError("DOCUMENT_CHUNK_CHARACTERS must be at least 1000.")

if not 0 <= DOCUMENT_CHUNK_OVERLAP < DOCUMENT_CHUNK_CHARACTERS:
    raise RuntimeError(
        "DOCUMENT_CHUNK_OVERLAP must be non-negative and smaller than "
        "DOCUMENT_CHUNK_CHARACTERS."
    )

if MAX_DOCUMENT_CHUNKS < 1:
    raise RuntimeError("MAX_DOCUMENT_CHUNKS must be at least 1.")

if PROVIDER_MAX_ATTEMPTS < 1:
    raise RuntimeError("PROVIDER_MAX_ATTEMPTS must be at least 1.")

if PROVIDER_RETRY_BASE_SECONDS < 0 or PROVIDER_RETRY_MAX_SECONDS < 0:
    raise RuntimeError("Provider retry delays cannot be negative.")


API_KEYS = {
    "openai": os.getenv("OPENAI_API_KEY"),
    "anthropic": os.getenv("ANTHROPIC_API_KEY"),
    "google": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
    "xai": os.getenv("XAI_API_KEY"),
}


MODEL_NAMES = {
    "openai": os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
    "anthropic": os.getenv(
        "ANTHROPIC_MODEL",
        "claude-sonnet-5",
    ),
    "google": os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash",
    ),
    "xai": os.getenv("XAI_MODEL", "grok-4.5"),
}


# OLLAMA_MODELS defines the startup defaults. The UI discovers every installed
# local model dynamically, so pulling a new model does not require code changes.
_ollama_models_value = os.getenv("OLLAMA_MODELS")

if _ollama_models_value is None:
    _ollama_models_value = os.getenv(
        "OLLAMA_MODEL",
        "qwen3.6:latest,qwen2.5-coder:7b",
    )

OLLAMA_MODELS = _csv_values(_ollama_models_value)


SUPPORTED_PROVIDERS = (
    "openai",
    "anthropic",
    "google",
    "xai",
    "ollama",
)

PROVIDERS_REQUIRING_KEYS = frozenset(API_KEYS.keys())

# These cloud models appear in the UI when their provider key is configured,
# even when the model is not part of the default council.
AVAILABLE_CLOUD_MODELS = [
    f"{provider}:{MODEL_NAMES[provider]}"
    for provider in ("openai", "anthropic", "google", "xai")
    if _is_configured_api_key(API_KEYS.get(provider))
]


# The safe default is local-only. Set COUNCIL_PROVIDERS explicitly in .env
# after adding real cloud API keys.
COUNCIL_PROVIDERS = _csv_values(
    os.getenv("COUNCIL_PROVIDERS", "ollama").lower()
)

if not COUNCIL_PROVIDERS:
    raise RuntimeError("COUNCIL_PROVIDERS must contain at least one provider.")


unknown_providers = [
    provider
    for provider in COUNCIL_PROVIDERS
    if provider not in SUPPORTED_PROVIDERS
]

if unknown_providers:
    raise RuntimeError(
        "Unsupported providers in COUNCIL_PROVIDERS: "
        + ", ".join(unknown_providers)
    )


missing_or_placeholder_keys = [
    provider
    for provider in COUNCIL_PROVIDERS
    if (
        provider in PROVIDERS_REQUIRING_KEYS
        and not _is_configured_api_key(API_KEYS.get(provider))
    )
]

if missing_or_placeholder_keys:
    raise RuntimeError(
        "Missing or placeholder API keys for configured providers: "
        + ", ".join(missing_or_placeholder_keys)
        + ". Add real keys to .env or remove those providers from "
        "COUNCIL_PROVIDERS."
    )

if "ollama" in COUNCIL_PROVIDERS and not OLLAMA_MODELS:
    raise RuntimeError(
        "Ollama is configured but OLLAMA_MODELS does not contain a model."
    )


# Model IDs use provider:model-name. Splitting on the first colon preserves
# Ollama tags such as ollama:qwen3.6:latest.
COUNCIL_MODELS: list[str] = []

for provider in COUNCIL_PROVIDERS:
    if provider == "ollama":
        COUNCIL_MODELS.extend(
            f"ollama:{model_name}"
            for model_name in OLLAMA_MODELS
        )
    else:
        COUNCIL_MODELS.append(
            f"{provider}:{MODEL_NAMES[provider]}"
        )

if not COUNCIL_MODELS:
    raise RuntimeError("No council models have been configured.")


CHAIRMAN_PROVIDER = os.getenv(
    "CHAIRMAN_PROVIDER",
    COUNCIL_PROVIDERS[0],
).strip().lower()

if CHAIRMAN_PROVIDER not in SUPPORTED_PROVIDERS:
    raise RuntimeError(
        f"Unsupported CHAIRMAN_PROVIDER: {CHAIRMAN_PROVIDER}"
    )

if (
    CHAIRMAN_PROVIDER in PROVIDERS_REQUIRING_KEYS
    and not _is_configured_api_key(API_KEYS.get(CHAIRMAN_PROVIDER))
):
    raise RuntimeError(
        "Missing or placeholder API key for chairman provider: "
        f"{CHAIRMAN_PROVIDER}"
    )

if CHAIRMAN_PROVIDER == "ollama":
    default_ollama_chairman = (
        OLLAMA_MODELS[0]
        if OLLAMA_MODELS
        else "qwen3.6:latest"
    )
    ollama_chairman_model = os.getenv(
        "OLLAMA_CHAIRMAN_MODEL",
        default_ollama_chairman,
    ).strip()

    if not ollama_chairman_model:
        raise RuntimeError("OLLAMA_CHAIRMAN_MODEL cannot be empty.")

    CHAIRMAN_MODEL = f"ollama:{ollama_chairman_model}"
else:
    CHAIRMAN_MODEL = (
        f"{CHAIRMAN_PROVIDER}:{MODEL_NAMES[CHAIRMAN_PROVIDER]}"
    )


# Use an installed, lightweight local model for titles by default. This avoids
# an extra billed cloud request for every new conversation.
TITLE_MODEL = os.getenv(
    "TITLE_MODEL",
    "ollama:llama3.1:latest",
).strip()

title_provider, separator, title_model_name = TITLE_MODEL.partition(":")
title_provider = title_provider.lower().strip()

if not separator or not title_model_name.strip():
    raise RuntimeError(
        "TITLE_MODEL must use the format provider:model-name."
    )

if title_provider not in SUPPORTED_PROVIDERS:
    raise RuntimeError(
        f"Unsupported provider in TITLE_MODEL: {title_provider}"
    )

if (
    title_provider in PROVIDERS_REQUIRING_KEYS
    and not _is_configured_api_key(API_KEYS.get(title_provider))
):
    raise RuntimeError(
        "Missing or placeholder API key for TITLE_MODEL provider: "
        f"{title_provider}"
    )

TITLE_MODEL_IS_LOCAL = (
    title_provider == "ollama"
    and OLLAMA_ENDPOINT_IS_LOCAL
    and not title_model_name.strip().endswith("-cloud")
)
