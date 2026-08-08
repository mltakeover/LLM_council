import asyncio

import httpx
import pytest

from backend import providers


@pytest.mark.asyncio
async def test_remote_ollama_models_are_not_marked_local(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "models": [
                    {"name": "qwen:7b", "size": 4_000_000_000},
                    {"name": "hosted-cloud", "size": 0},
                ],
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url):
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(providers, "OLLAMA_ENDPOINT_IS_LOCAL", False)

    models = await providers.list_ollama_models()
    remote = next(model for model in models if model["name"] == "qwen:7b")
    hosted = next(model for model in models if model["name"] == "hosted-cloud")

    assert remote["source"] == "remote-ollama"
    assert remote["is_local"] is False
    assert remote["selectable"] is True
    assert hosted["source"] == "ollama-cloud"
    assert hosted["selectable"] is False


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
    monkeypatch.setattr(providers, "_retry_delay", lambda *_args, **_kwargs: 0)

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
    assert result["error"]["code"] == "timeout"
    assert result["error"]["message"] == "too slow"
    assert result["error"]["retryable"] is True
    assert result["error"]["status_code"] is None
    assert result["error"]["exception_type"] == "TimeoutError"
    assert result["error"]["retry_after_seconds"] is None
    # Errors now carry user-facing guidance alongside the machine-readable code.
    assert result["error"]["cause"]
    assert result["error"]["fix"]


@pytest.mark.asyncio
async def test_query_model_rejects_unknown_provider_without_retry() -> None:
    result = await providers.query_model(
        "unknown:model",
        [{"role": "user", "content": "Review this"}],
    )

    assert result["ok"] is False
    assert result["attempts"] == 0
    assert result["error"]["code"] == "configuration"


@pytest.mark.asyncio
async def test_quota_error_is_not_retried(monkeypatch) -> None:
    """A billing 429 must fail on the first attempt.

    Retrying wastes PROVIDER_MAX_ATTEMPTS and the full backoff delay on a
    condition that only a credit top-up can clear.
    """

    calls = 0

    async def failing_query(model_name, messages):
        nonlocal calls
        calls += 1
        error = Exception(
            "Error code: 429 - {'error': {'message': 'You exceeded your current "
            "quota, please check your plan and billing details.', 'code': "
            "'insufficient_quota'}}"
        )
        error.status_code = 429
        raise error

    monkeypatch.setattr(providers, "_query_openai", failing_query)
    monkeypatch.setattr(providers, "PROVIDER_MAX_ATTEMPTS", 3)

    result = await providers.query_model("openai:gpt-5.6-terra", [])

    assert result["ok"] is False
    assert calls == 1
    assert result["error"]["code"] == "quota_exhausted"
    assert result["error"]["retryable"] is False
    assert result["error"]["fix"]


@pytest.mark.asyncio
async def test_rate_limit_error_is_retried(monkeypatch) -> None:
    """The counterpart: an identical status code that should be retried."""

    calls = 0

    async def flaky_query(model_name, messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            error = Exception(
                "Error code: 429 - {'error': {'message': 'Rate limit reached "
                "for gpt-5.6-terra.', 'code': 'rate_limit_exceeded'}}"
            )
            error.status_code = 429
            raise error
        return {"content": "ok", "usage": None}

    monkeypatch.setattr(providers, "_query_openai", flaky_query)
    monkeypatch.setattr(providers, "PROVIDER_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(providers, "_retry_delay", lambda *_args, **_kwargs: 0)

    result = await providers.query_model("openai:gpt-5.6-terra", [])

    assert result["ok"] is True
    assert calls == 2
    assert result["attempts"] == 2


@pytest.mark.asyncio
async def test_long_retry_after_stops_retrying_and_reports_the_wait(monkeypatch) -> None:
    """A provider asking for longer than the ceiling must not stall the council.

    Sleeping through it blocks every other seat; shortening it guarantees
    another rejection. Failing with the wait time is the only useful option.
    """

    calls = 0

    async def rate_limited(model_name, messages):
        nonlocal calls
        calls += 1
        error = Exception(
            "Error code: 429 - {'error': {'message': 'Rate limit reached.', "
            "'code': 'rate_limit_exceeded'}}"
        )
        error.status_code = 429
        error.response = type(
            "R", (), {"status_code": 429, "headers": {"retry-after": "300"}, "text": ""}
        )()
        raise error

    monkeypatch.setattr(providers, "_query_openai", rate_limited)
    monkeypatch.setattr(providers, "PROVIDER_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(providers, "PROVIDER_RETRY_AFTER_MAX_SECONDS", 30)

    result = await providers.query_model("openai:gpt-5.6-terra", [])

    assert result["ok"] is False
    assert calls == 1
    assert result["error"]["retry_after_seconds"] == 300.0
    assert result["error"]["retryable"] is False
    assert "300" in result["error"]["fix"]


def test_retry_delay_honours_retry_after_in_full(monkeypatch) -> None:
    """Regression: the delay used to be clamped to PROVIDER_RETRY_MAX_SECONDS."""

    monkeypatch.setattr(providers, "PROVIDER_RETRY_MAX_SECONDS", 8)

    assert providers._retry_delay(1, retry_after=25) == 25.0
