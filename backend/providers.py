"""Direct clients for cloud LLM providers and local Ollama models."""

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from .config import (
    ANTHROPIC_MAX_TOKENS,
    API_KEYS,
    OLLAMA_BASE_URL,
    OLLAMA_DISCOVERY_TIMEOUT,
    OLLAMA_MAX_CONCURRENCY,
    PROVIDER_MAX_ATTEMPTS,
    PROVIDER_RETRY_BASE_SECONDS,
    PROVIDER_RETRY_MAX_SECONDS,
    REQUEST_TIMEOUT,
)

Message = Dict[str, str]
ModelResult = Dict[str, Any]
EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]

logger = logging.getLogger(__name__)


_openai_client = (
    AsyncOpenAI(api_key=API_KEYS["openai"])
    if API_KEYS.get("openai")
    else None
)

_anthropic_client = (
    AsyncAnthropic(api_key=API_KEYS["anthropic"])
    if API_KEYS.get("anthropic")
    else None
)

_google_client = (
    genai.Client(api_key=API_KEYS["google"])
    if API_KEYS.get("google")
    else None
)

_xai_client = (
    AsyncOpenAI(
        api_key=API_KEYS["xai"],
        base_url="https://api.x.ai/v1",
    )
    if API_KEYS.get("xai")
    else None
)

_ollama_client = AsyncOpenAI(
    api_key="ollama",
    base_url=OLLAMA_BASE_URL.rstrip("/") + "/",
)

_ollama_semaphore = asyncio.Semaphore(OLLAMA_MAX_CONCURRENCY)


def _split_model_id(model_id: str) -> Tuple[str, str]:
    """Convert 'provider:model-name' into its two components."""

    if ":" not in model_id:
        raise ValueError(
            f"Invalid model identifier '{model_id}'. "
            "Expected 'provider:model-name'."
        )

    provider, model_name = model_id.split(":", 1)
    return provider.lower().strip(), model_name.strip()


def _ollama_native_url(path: str) -> str:
    """Build a native Ollama URL from the configured OpenAI-compatible URL."""

    parsed = urlsplit(OLLAMA_BASE_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("OLLAMA_BASE_URL must be an absolute HTTP URL.")

    return f"{parsed.scheme}://{parsed.netloc}{path}"


async def list_ollama_models() -> List[Dict[str, Any]]:
    """Discover models currently registered with the local Ollama service."""

    async with httpx.AsyncClient(timeout=OLLAMA_DISCOVERY_TIMEOUT) as client:
        response = await client.get(_ollama_native_url("/api/tags"))
        response.raise_for_status()

    payload = response.json()
    discovered = []

    for item in payload.get("models", []):
        model_name = item.get("name") or item.get("model")
        if not model_name:
            continue

        size = int(item.get("size") or 0)
        is_cloud = model_name.endswith("-cloud") or size <= 0
        details = item.get("details") or {}

        discovered.append({
            "id": f"ollama:{model_name}",
            "name": model_name,
            "provider": "ollama",
            "source": "ollama-cloud" if is_cloud else "local",
            "is_local": not is_cloud,
            "is_cloud": is_cloud,
            "selectable": not is_cloud,
            "size": size,
            "parameter_size": details.get("parameter_size"),
            "quantization": details.get("quantization_level"),
            "modified_at": item.get("modified_at"),
        })

    return sorted(
        discovered,
        key=lambda model: (model["is_cloud"], model["name"].lower()),
    )


def _system_prompt(messages: List[Message]) -> str:
    return "\n\n".join(
        message.get("content", "")
        for message in messages
        if message.get("role") == "system"
    )


async def _query_openai(
    model_name: str,
    messages: List[Message],
) -> ModelResult:
    if _openai_client is None:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    response = await _openai_client.chat.completions.create(
        model=model_name,
        messages=messages,  # type: ignore[arg-type]
        store=False,
    )

    return {
        "content": response.choices[0].message.content or "",
        "reasoning_details": None,
    }


async def _query_anthropic(
    model_name: str,
    messages: List[Message],
) -> ModelResult:
    if _anthropic_client is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

    system_prompt = _system_prompt(messages)
    anthropic_messages = [
        {
            "role": (
                "assistant"
                if message.get("role") == "assistant"
                else "user"
            ),
            "content": message.get("content", ""),
        }
        for message in messages
        if message.get("role") != "system"
    ]

    if not anthropic_messages:
        anthropic_messages = [
            {"role": "user", "content": "Please continue."}
        ]

    request: Dict[str, Any] = {
        "model": model_name,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": anthropic_messages,
    }

    if system_prompt:
        request["system"] = system_prompt

    response = await _anthropic_client.messages.create(**request)
    content = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )

    return {
        "content": content,
        "reasoning_details": None,
    }


async def _query_google(
    model_name: str,
    messages: List[Message],
) -> ModelResult:
    if _google_client is None:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY is not configured."
        )

    system_prompt = _system_prompt(messages)
    contents = [
        types.Content(
            role=(
                "model"
                if message.get("role") == "assistant"
                else "user"
            ),
            parts=[
                types.Part.from_text(
                    text=message.get("content", "")
                )
            ],
        )
        for message in messages
        if message.get("role") != "system"
    ]

    if not contents:
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="Please continue.")],
            )
        ]

    request: Dict[str, Any] = {
        "model": model_name,
        "contents": contents,
    }

    if system_prompt:
        request["config"] = types.GenerateContentConfig(
            system_instruction=system_prompt
        )

    response = await _google_client.aio.models.generate_content(**request)

    return {
        "content": response.text or "",
        "reasoning_details": None,
    }


async def _query_xai(
    model_name: str,
    messages: List[Message],
) -> ModelResult:
    if _xai_client is None:
        raise RuntimeError("XAI_API_KEY is not configured.")

    response = await _xai_client.chat.completions.create(
        model=model_name,
        messages=messages,  # type: ignore[arg-type]
    )

    return {
        "content": response.choices[0].message.content or "",
        "reasoning_details": None,
    }


async def _query_ollama(
    model_name: str,
    messages: List[Message],
) -> ModelResult:
    """Query an Ollama model through its local OpenAI-compatible API."""

    async with _ollama_semaphore:
        response = await _ollama_client.chat.completions.create(
            model=model_name,
            messages=messages,  # type: ignore[arg-type]
        )

    message = response.choices[0].message
    reasoning_details = getattr(message, "reasoning", None)

    if reasoning_details is None:
        model_extra = getattr(message, "model_extra", None) or {}
        reasoning_details = (
            model_extra.get("reasoning")
            or model_extra.get("reasoning_content")
        )

    return {
        "content": message.content or "",
        "reasoning_details": reasoning_details,
    }


async def _emit(
    callback: Optional[EventCallback],
    event_type: str,
    data: Dict[str, Any],
) -> None:
    if callback is not None:
        await callback({"type": event_type, "data": data})


def _status_code(exc: Exception) -> Optional[int]:
    value = getattr(exc, "status_code", None)
    if value is None:
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)

    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _error_details(exc: Exception) -> Dict[str, Any]:
    status_code = _status_code(exc)
    exception_name = type(exc).__name__
    lowered_name = exception_name.lower()

    if isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
        code = "timeout"
        retryable = True
    elif status_code == 429:
        code = "rate_limit"
        retryable = True
    elif status_code in {500, 502, 503, 504}:
        code = "provider_unavailable"
        retryable = True
    elif status_code in {401, 403}:
        code = "authentication"
        retryable = False
    elif status_code == 404:
        code = "model_not_found"
        retryable = False
    elif status_code == 400:
        code = "invalid_request"
        retryable = False
    elif (
        isinstance(exc, (httpx.NetworkError, ConnectionError, OSError))
        or "connection" in lowered_name
    ):
        code = "connection"
        retryable = True
    elif isinstance(exc, ValueError):
        code = "configuration"
        retryable = False
    else:
        code = "provider_error"
        retryable = False

    message = " ".join(str(exc).split())[:500]
    if not message:
        message = exception_name

    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "status_code": status_code,
        "exception_type": exception_name,
    }


def _retry_delay(attempt: int) -> float:
    base = PROVIDER_RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1))
    capped = min(base, PROVIDER_RETRY_MAX_SECONDS)
    return round(capped + random.uniform(0, capped * 0.2), 3)


async def query_model(
    model: str,
    messages: List[Message],
    timeout: float = REQUEST_TIMEOUT,
    event_callback: Optional[EventCallback] = None,
    stage: Optional[str] = None,
) -> ModelResult:
    """Query one provider and always return a structured success/failure."""

    started_at = time.monotonic()
    stage_name = stage or "provider"
    await _emit(
        event_callback,
        "model_started",
        {"model": model, "stage": stage_name},
    )

    try:
        provider, model_name = _split_model_id(model)
    except Exception as exc:
        error = _error_details(exc)
        result = {
            "ok": False,
            "model": model,
            "provider": None,
            "content": "",
            "reasoning_details": None,
            "attempts": 0,
            "elapsed_seconds": 0.0,
            "error": error,
        }
        await _emit(
            event_callback,
            "model_failed",
            {"model": model, "stage": stage_name, **result},
        )
        return result

    handlers = {
        "openai": _query_openai,
        "anthropic": _query_anthropic,
        "google": _query_google,
        "xai": _query_xai,
        "ollama": _query_ollama,
    }
    handler = handlers.get(provider)

    if handler is None:
        error = _error_details(ValueError(f"Unsupported provider: {provider}"))
        result = {
            "ok": False,
            "model": model,
            "provider": provider,
            "content": "",
            "reasoning_details": None,
            "attempts": 0,
            "elapsed_seconds": 0.0,
            "error": error,
        }
        await _emit(
            event_callback,
            "model_failed",
            {"model": model, "stage": stage_name, **result},
        )
        return result

    last_error: Dict[str, Any] = {
        "code": "provider_error",
        "message": "Provider request failed.",
        "retryable": False,
        "status_code": None,
        "exception_type": "UnknownError",
    }

    attempts_made = 0
    for attempt in range(1, PROVIDER_MAX_ATTEMPTS + 1):
        attempts_made = attempt
        try:
            provider_result = await asyncio.wait_for(
                handler(model_name, messages),
                timeout=timeout,
            )

            if not provider_result.get("content", "").strip():
                raise RuntimeError("Provider returned an empty response.")

            result = {
                "ok": True,
                "model": model,
                "provider": provider,
                "content": provider_result.get("content", ""),
                "reasoning_details": provider_result.get("reasoning_details"),
                "attempts": attempt,
                "elapsed_seconds": round(time.monotonic() - started_at, 2),
                "error": None,
            }
            await _emit(
                event_callback,
                "model_completed",
                {"model": model, "stage": stage_name, **result},
            )
            return result

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = _error_details(exc)
            if str(exc) == "Provider returned an empty response.":
                last_error["code"] = "empty_response"
                last_error["retryable"] = True

            logger.warning(
                "Provider call failed model=%s stage=%s attempt=%s/%s "
                "code=%s status=%s error=%s",
                model,
                stage_name,
                attempt,
                PROVIDER_MAX_ATTEMPTS,
                last_error["code"],
                last_error["status_code"],
                last_error["message"],
            )

            can_retry = (
                last_error["retryable"]
                and attempt < PROVIDER_MAX_ATTEMPTS
            )
            if not can_retry:
                break

            delay = _retry_delay(attempt)
            await _emit(
                event_callback,
                "model_retrying",
                {
                    "model": model,
                    "stage": stage_name,
                    "attempt": attempt + 1,
                    "delay_seconds": delay,
                    "error": last_error,
                },
            )
            await asyncio.sleep(delay)

    result = {
        "ok": False,
        "model": model,
        "provider": provider,
        "content": "",
        "reasoning_details": None,
        "attempts": attempts_made,
        "elapsed_seconds": round(time.monotonic() - started_at, 2),
        "error": last_error,
    }
    await _emit(
        event_callback,
        "model_failed",
        {"model": model, "stage": stage_name, **result},
    )
    return result


async def query_models_parallel(
    models: List[str],
    messages: List[Message],
    event_callback: Optional[EventCallback] = None,
    stage: Optional[str] = None,
    messages_by_model: Optional[Dict[str, List[Message]]] = None,
) -> Dict[str, ModelResult]:
    """Query all council members concurrently."""

    responses = await asyncio.gather(
        *[
            query_model(
                model,
                (messages_by_model or {}).get(model, messages),
                event_callback=event_callback,
                stage=stage,
            )
            for model in models
        ]
    )
    return dict(zip(models, responses, strict=True))
