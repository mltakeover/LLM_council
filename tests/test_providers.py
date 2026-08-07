import asyncio

import httpx
import pytest

from backend import providers


@pytest.mark.asyncio
async def test_query_model_retries_then_emits_completion(monkeypatch) -> None:
    calls = 0
    events = []

    async def flaky_query(_model_name, _messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary connection failure")
        return {
            "content": "review complete",
            "reasoning_details": None,
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        }

    async def capture(event):
        events.append(event)

    monkeypatch.setattr(providers, "_query_ollama", flaky_query)
    monkeypatch.setattr(providers, "PROVIDER_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(providers, "_retry_delay", lambda _attempt: 0)

    result = await providers.query_model(
        "ollama:test-model",
        [{"role": "user", "content": "Review this"}],
        event_callback=capture,
        stage="stage1",
    )

    assert result["ok"] is True
    assert result["attempts"] == 2
    assert result["usage"]["total_tokens"] == 14
    assert [event["type"] for event in events] == [
        "model_started",
        "model_retrying",
        "model_completed",
    ]
    assert events[1]["data"]["error"]["code"] == "connection"


@pytest.mark.asyncio
async def test_query_model_returns_structured_timeout(monkeypatch) -> None:
    async def timed_out(_model_name, _messages):
        raise asyncio.TimeoutError("too slow")

    monkeypatch.setattr(providers, "_query_ollama", timed_out)
    monkeypatch.setattr(providers, "PROVIDER_MAX_ATTEMPTS", 1)

    result = await providers.query_model(
        "ollama:test-model",
        [{"role": "user", "content": "Review this"}],
    )

    assert result["ok"] is False
    assert result["attempts"] == 1
    assert result["error"] == {
        "code": "timeout",
        "message": "too slow",
        "retryable": True,
        "status_code": None,
        "exception_type": "TimeoutError",
    }


@pytest.mark.asyncio
async def test_query_model_rejects_unknown_provider_without_retry() -> None:
    result = await providers.query_model(
        "unknown:model",
        [{"role": "user", "content": "Review this"}],
    )

    assert result["ok"] is False
    assert result["attempts"] == 0
    assert result["error"]["code"] == "configuration"
