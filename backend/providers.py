"""Direct clients for cloud LLM providers and local Ollama models."""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from .config import (
    ANTHROPIC_MAX_TOKENS,
    API_KEYS,
    OLLAMA_BASE_URL,
    OLLAMA_MAX_CONCURRENCY,
    REQUEST_TIMEOUT,
)


Message = Dict[str, str]
ModelResult = Dict[str, Any]


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

# xAI exposes an OpenAI-compatible API.
_xai_client = (
    AsyncOpenAI(
        api_key=API_KEYS["xai"],
        base_url="https://api.x.ai/v1",
    )
    if API_KEYS.get("xai")
    else None
)

# Ollama exposes an OpenAI-compatible local API. The OpenAI SDK requires an
# api_key value, but Ollama ignores this placeholder for localhost requests.
_ollama_client = AsyncOpenAI(
    api_key="ollama",
    base_url=OLLAMA_BASE_URL.rstrip("/") + "/",
)

# Multiple Ollama tasks may be scheduled together by the council and title
# generator. Serial execution avoids unnecessary model swapping and memory
# pressure. Increase OLLAMA_MAX_CONCURRENCY only after testing your machine.
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


def _system_prompt(messages: List[Message]) -> str:
    """Combine system messages for providers that take a separate instruction."""

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
        # Prevents stored application state. It is not the same as ZDR.
        store=False,
    )

    content = response.choices[0].message.content or ""

    return {
        "content": content,
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
                parts=[
                    types.Part.from_text(text="Please continue.")
                ],
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

    response = await _google_client.aio.models.generate_content(
        **request
    )

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

    content = response.choices[0].message.content or ""

    return {
        "content": content,
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
    content = message.content or ""

    # Ollama thinking models may return reasoning as an extra response field.
    reasoning_details = getattr(message, "reasoning", None)

    if reasoning_details is None:
        model_extra = getattr(message, "model_extra", None) or {}
        reasoning_details = (
            model_extra.get("reasoning")
            or model_extra.get("reasoning_content")
        )

    return {
        "content": content,
        "reasoning_details": reasoning_details,
    }


async def query_model(
    model: str,
    messages: List[Message],
    timeout: float = REQUEST_TIMEOUT,
) -> Optional[ModelResult]:
    """Query one directly configured cloud or local provider."""

    try:
        provider, model_name = _split_model_id(model)

        handlers = {
            "openai": _query_openai,
            "anthropic": _query_anthropic,
            "google": _query_google,
            "xai": _query_xai,
            "ollama": _query_ollama,
        }

        handler = handlers.get(provider)

        if handler is None:
            raise ValueError(f"Unsupported provider: {provider}")

        result = await asyncio.wait_for(
            handler(model_name, messages),
            timeout=timeout,
        )

        if not result.get("content", "").strip():
            print(f"Provider returned no text: {model}")
            return None

        return result

    except asyncio.TimeoutError:
        print(f"Timeout querying {model} after {timeout} seconds")
        return None

    except Exception as exc:
        print(
            f"Error querying {model}: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Message],
) -> Dict[str, Optional[ModelResult]]:
    """Query all council members concurrently."""

    responses = await asyncio.gather(
        *[
            query_model(model, messages)
            for model in models
        ]
    )

    return dict(zip(models, responses))

