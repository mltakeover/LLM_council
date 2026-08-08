"""Tests for actionable provider error diagnosis."""

from backend.errors import (
    diagnose,
    extract_provider_message,
    extract_retry_after,
    parse_retry_after_value,
)


class FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None, text: str = ""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


class FakeProviderError(Exception):
    """Mimics how provider SDKs stringify a nested error payload."""

    def __init__(self, message: str, status_code: int | None = None, headers=None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
            self.response = FakeResponse(status_code, headers, message)


RATE_LIMIT_429 = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-5.6-terra "
    "in organization org-abc on requests per min (RPM): Limit 500, Used 500.', "
    "'type': 'requests', 'code': 'rate_limit_exceeded'}}"
)

QUOTA_429 = (
    "Error code: 429 - {'error': {'message': 'You exceeded your current quota, "
    "please check your plan and billing details.', 'type': 'insufficient_quota', "
    "'code': 'insufficient_quota'}}"
)


def test_rate_limit_429_is_retryable() -> None:
    diagnosis = diagnose(FakeProviderError(RATE_LIMIT_429, 429), 429)

    assert diagnosis.code == "rate_limit"
    assert diagnosis.retryable is True


def test_quota_429_is_not_retryable() -> None:
    """The regression this module exists for.

    Both errors are HTTP 429, but retrying a billing failure can never succeed.
    Classifying on status code alone conflates them.
    """

    diagnosis = diagnose(FakeProviderError(QUOTA_429, 429), 429)

    assert diagnosis.code == "quota_exhausted"
    assert diagnosis.retryable is False


def test_payment_required_maps_to_quota() -> None:
    exc = FakeProviderError("Error code: 402 - Insufficient credits.", 402)

    assert diagnose(exc, 402).code == "quota_exhausted"


def test_context_length_is_detected_from_body_not_status() -> None:
    exc = FakeProviderError(
        "Error code: 400 - {'error': {'message': \"This model's maximum context "
        "length is 128000 tokens, however you requested 190210.\", "
        "'code': 'context_length_exceeded'}}",
        400,
    )

    diagnosis = diagnose(exc, 400)

    assert diagnosis.code == "context_length"
    assert diagnosis.retryable is False


def test_missing_ollama_model_is_classified() -> None:
    exc = FakeProviderError(
        "model 'qwen3.6:latest' not found, try pulling it first", 404
    )

    assert diagnose(exc, 404).code == "model_not_found"


def test_invalid_key_is_authentication() -> None:
    exc = FakeProviderError(
        "Error code: 401 - {'error': {'message': 'Incorrect API key provided.'}}", 401
    )

    assert diagnose(exc, 401).code == "authentication"


def test_unknown_error_falls_back_without_claiming_retryable() -> None:
    diagnosis = diagnose(Exception("something inexplicable"), None)

    assert diagnosis.code == "provider_error"
    assert diagnosis.retryable is False


def test_every_diagnosis_carries_a_cause_and_a_fix() -> None:
    """A code without guidance is what made the original error unhelpful."""

    for exc, status in (
        (FakeProviderError(RATE_LIMIT_429, 429), 429),
        (FakeProviderError(QUOTA_429, 429), 429),
        (Exception("unclassifiable"), None),
    ):
        diagnosis = diagnose(exc, status)
        assert diagnosis.cause.strip()
        assert diagnosis.fix.strip()


def test_provider_message_is_unwrapped_from_its_envelope() -> None:
    """The nested dict is what gets truncated into an unreadable stub."""

    message = extract_provider_message(FakeProviderError(QUOTA_429, 429))

    assert message.startswith("You exceeded your current quota")
    assert "{" not in message


def test_provider_message_survives_a_plain_string() -> None:
    assert extract_provider_message(Exception("connection refused")) == (
        "connection refused"
    )


def test_retry_after_header_is_read() -> None:
    exc = FakeProviderError(RATE_LIMIT_429, 429, {"retry-after": "12"})

    assert extract_retry_after(exc) == 12.0


def test_retry_after_is_none_when_absent() -> None:
    assert extract_retry_after(FakeProviderError(RATE_LIMIT_429, 429)) is None


def test_retry_after_plain_seconds() -> None:
    exc = FakeProviderError(RATE_LIMIT_429, 429, {"retry-after": "30"})

    assert extract_retry_after(exc) == 30.0


def test_retry_after_is_not_shortened_by_the_backoff_cap() -> None:
    """Regression: Retry-After is a minimum, not a target.

    Clamping a 30s request down to an 8s backoff ceiling guarantees the retry
    arrives early and is rejected again.
    """

    exc = FakeProviderError(RATE_LIMIT_429, 429, {"retry-after": "45"})

    assert extract_retry_after(exc) == 45.0


def test_retry_after_accepts_an_http_date() -> None:
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    when = datetime.now(timezone.utc) + timedelta(seconds=60)
    exc = FakeProviderError(RATE_LIMIT_429, 429, {"retry-after": format_datetime(when)})

    seconds = extract_retry_after(exc)

    assert seconds is not None
    assert 55 <= seconds <= 61


def test_retry_after_http_date_in_the_past_is_zero() -> None:
    exc = FakeProviderError(
        RATE_LIMIT_429, 429, {"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}
    )

    assert extract_retry_after(exc) == 0.0


def test_retry_after_parses_compound_and_subsecond_durations() -> None:
    assert parse_retry_after_value("1m30s") == 90.0
    assert parse_retry_after_value("250ms") == 0.25
    assert parse_retry_after_value("2.5s") == 2.5


def test_retry_after_rejects_unparseable_values() -> None:
    """Falling back to backoff is safer than inventing a wait."""

    assert parse_retry_after_value("soon") is None
    assert parse_retry_after_value("") is None
