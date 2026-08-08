"""Actionable diagnosis of provider failures.

A raw provider error such as ``Error code: 429`` is not actionable, because a
429 means one of two opposite things:

* the request rate was too high — waiting will fix it, or
* the account has no remaining credit — waiting will never fix it.

Classifying both as ``rate_limit`` causes pointless retries against a billing
problem and reports a misleading cause to the user. This module inspects the
provider's message body before falling back to the HTTP status code, and pairs
every category with a plain-English cause and a concrete fix.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional, Tuple


@dataclass(frozen=True)
class Diagnosis:
    """A classified failure, described in terms the user can act on."""

    code: str
    cause: str
    fix: str
    retryable: bool


DIAGNOSES: dict[str, Diagnosis] = {
    "authentication": Diagnosis(
        code="authentication",
        cause="The API key was rejected, is missing, or has no access to this model.",
        fix=(
            "Check the provider's key in .env. If the key is valid, confirm the model "
            "is enabled for your account — some providers gate newer models behind a "
            "separate opt-in."
        ),
        retryable=False,
    ),
    "rate_limit": Diagnosis(
        code="rate_limit",
        cause="Requests were sent faster than this model's rate limit allows.",
        fix=(
            "This retries automatically with backoff. If it keeps failing, reduce the "
            "number of council models using the same provider, or raise "
            "PROVIDER_RETRY_MAX_SECONDS in .env."
        ),
        retryable=True,
    ),
    "quota_exhausted": Diagnosis(
        code="quota_exhausted",
        cause=(
            "The account has no remaining credit or has hit a hard spend cap. This is "
            "a billing state, not a speed limit, so retrying cannot succeed."
        ),
        fix=(
            "Top up the credit balance or raise the spend cap in the provider's "
            "dashboard. To keep working meanwhile, remove that provider from "
            "COUNCIL_PROVIDERS in .env and rely on the local Ollama models."
        ),
        retryable=False,
    ),
    "model_not_found": Diagnosis(
        code="model_not_found",
        cause=(
            "The model identifier does not exist at this provider. Model names are "
            "retired and renamed more often than anything else in the config."
        ),
        fix=(
            "Correct the model name in .env (for example OPENAI_MODEL or "
            "OLLAMA_MODELS). For local models, run `ollama list` to see what is "
            "actually installed, then `ollama pull <model>` if it is missing."
        ),
        retryable=False,
    ),
    "provider_unavailable": Diagnosis(
        code="provider_unavailable",
        cause="The provider accepted the request but could not serve it.",
        fix=(
            "Usually transient and retried automatically. If it persists, the provider "
            "is having an incident — check their status page."
        ),
        retryable=True,
    ),
    "context_length": Diagnosis(
        code="context_length",
        cause="The prompt and attached documents exceeded this model's context window.",
        fix=(
            "Lower MAX_CONTEXT_CHARACTERS or MAX_DOCUMENT_CHUNKS in .env, attach fewer "
            "documents, or move this seat to a longer-context model. Local models "
            "typically have far smaller windows than cloud ones."
        ),
        retryable=False,
    ),
    "content_filter": Diagnosis(
        code="content_filter",
        cause="The provider's safety filter blocked the request or the response.",
        fix=(
            "Often a false positive on security or infrastructure wording. Route this "
            "seat to a different provider, or review the document section that "
            "triggered it."
        ),
        retryable=False,
    ),
    "timeout": Diagnosis(
        code="timeout",
        cause="The model did not respond within the timeout.",
        fix=(
            "Retried automatically. Large documents on local models are the usual "
            "cause — raise REQUEST_TIMEOUT in .env or reduce the document size."
        ),
        retryable=True,
    ),
    "connection": Diagnosis(
        code="connection",
        cause="The provider endpoint could not be reached.",
        fix=(
            "Check network access. For local models, confirm Ollama is running with "
            "`ollama list` and that OLLAMA_BASE_URL matches the port it is serving on."
        ),
        retryable=True,
    ),
    "invalid_request": Diagnosis(
        code="invalid_request",
        cause="The provider rejected the request as malformed.",
        fix=(
            "See the provider response below — it usually names the offending "
            "parameter. This is a bug rather than a configuration problem if the same "
            "request works on another provider."
        ),
        retryable=False,
    ),
    "configuration": Diagnosis(
        code="configuration",
        cause="The council is misconfigured, so the request was never sent.",
        fix="Check COUNCIL_PROVIDERS and the model names in .env.",
        retryable=False,
    ),
    "provider_error": Diagnosis(
        code="provider_error",
        cause="The call failed for a reason that could not be classified.",
        fix=(
            "See the full provider response below — it usually names the problem. "
            "Please open an issue with that text so this case can be classified."
        ),
        retryable=False,
    ),
}


# Checked in order, against the provider's message body. Body text is more
# reliable than the status code, which is why it wins.
_SIGNATURES: Tuple[Tuple[str, str], ...] = (
    ("insufficient_quota", "quota_exhausted"),
    ("insufficient credit", "quota_exhausted"),
    ("insufficient_credits", "quota_exhausted"),
    ("exceeded your current quota", "quota_exhausted"),
    ("credit balance", "quota_exhausted"),
    ("billing", "quota_exhausted"),
    ("payment required", "quota_exhausted"),
    ("spend limit", "quota_exhausted"),
    ("quota exceeded", "quota_exhausted"),
    ("rate limit", "rate_limit"),
    ("rate_limit", "rate_limit"),
    ("too many requests", "rate_limit"),
    ("context length", "context_length"),
    ("context_length_exceeded", "context_length"),
    ("maximum context", "context_length"),
    ("too many tokens", "context_length"),
    ("reduce the length", "context_length"),
    ("content filter", "content_filter"),
    ("content_policy", "content_filter"),
    ("content_filter", "content_filter"),
    ("blocked by safety", "content_filter"),
    ("no endpoints found", "provider_unavailable"),
    ("overloaded", "provider_unavailable"),
    ("is not a valid model", "model_not_found"),
    ("model not found", "model_not_found"),
    ("unknown model", "model_not_found"),
    ("does not exist", "model_not_found"),
    ("try pulling it first", "model_not_found"),
    ("invalid api key", "authentication"),
    ("incorrect api key", "authentication"),
    ("unauthorized", "authentication"),
    ("no auth credentials", "authentication"),
)


_STATUS_CODES: dict[int, str] = {
    400: "invalid_request",
    401: "authentication",
    402: "quota_exhausted",
    403: "authentication",
    404: "model_not_found",
    408: "timeout",
    413: "context_length",
    422: "invalid_request",
    429: "rate_limit",
    500: "provider_unavailable",
    502: "provider_unavailable",
    503: "provider_unavailable",
    504: "timeout",
}


_STATUS_PATTERN = re.compile(r"(?:error code|status)[:\s]*(\d{3})", re.IGNORECASE)


def extract_provider_message(exc: BaseException) -> str:
    """Return the provider's own message, unwrapped from its envelope.

    Provider SDKs stringify a nested dict, so the useful sentence is buried
    inside something like ``Error code: 429 - {'error': {'message': ...}}``.
    Truncating that string is what produces an unreadable ``{'error': {'me...``.
    """

    text = str(exc)

    response = getattr(exc, "response", None)
    body = getattr(response, "text", None)
    if isinstance(body, str) and body.strip():
        text = body

    start = text.find("{")
    if start != -1:
        candidate = text[start:]
        for parser in (json.loads, ast.literal_eval):
            try:
                payload = parser(candidate)
            except (ValueError, SyntaxError, TypeError):
                continue
            message = _dig_message(payload)
            if message:
                return " ".join(message.split())

    return " ".join(text.split())


def _dig_message(payload: Any) -> str:
    """Find the deepest human-readable message in a provider error payload."""

    if isinstance(payload, dict):
        for key in ("message", "error", "detail", "msg"):
            if key in payload:
                found = _dig_message(payload[key])
                if found:
                    return found
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            raw = metadata.get("raw")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return ""


# A single "<number><unit>" token. The unit is required, so this cannot match a
# bare number lifted out of surrounding prose.
#
# Validation deliberately does not use an anchored repeating pattern such as
# `\A(?:\s*\d+\s*(?:ms|s|m|h)\s*)+\Z`. The trailing and leading `\s*` in that
# form can both match the same whitespace, making the group ambiguous and the
# match exponential on input that ultimately fails. Coverage is checked by
# scanning the token spans instead, which is linear.
_DURATION_TOKEN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|m|h)",
    re.IGNORECASE,
)

_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_retry_after_value(value: str) -> Optional[float]:
    """Parse one Retry-After style value into seconds.

    Three formats occur in the wild and all three must be handled:

    * plain seconds — ``"30"``
    * an HTTP-date, per RFC 9110 — ``"Wed, 21 Oct 2026 07:28:00 GMT"``
    * compound or sub-second durations used by rate-limit reset headers —
      ``"1m30s"``, ``"250ms"``

    A value is only accepted when the *entire* string is a valid duration.
    Provider headers are not user input, but they are not schema-checked either,
    and a number lifted out of surrounding prose is not a wait instruction.

    Returning ``None`` for an unparseable value is deliberate: guessing a wait
    is worse than falling back to exponential backoff.
    """

    text = str(value).strip()
    if not text:
        return None

    try:
        seconds = float(text)
    except ValueError:
        pass
    else:
        return seconds if seconds >= 0 else None

    # parsedate_to_datetime returns None on some versions and raises on others,
    # so both outcomes are treated as "not a date".
    try:
        parsed_date = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed_date = None

    if parsed_date is not None:
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        delta = (parsed_date - datetime.now(timezone.utc)).total_seconds()
        return max(delta, 0.0)

    # Every non-whitespace character must belong to a duration token. Anything
    # left over means this is prose that happens to contain a number, not a
    # wait instruction. Scanning spans keeps this linear in the input length.
    tokens = list(_DURATION_TOKEN.finditer(text))
    if not tokens:
        return None

    position = 0
    total = 0.0
    for match in tokens:
        if text[position:match.start()].strip():
            return None
        total += float(match.group("value")) * _UNIT_SECONDS[match.group("unit").lower()]
        position = match.end()

    if text[position:].strip():
        return None

    return total


def extract_retry_after(exc: BaseException) -> Optional[float]:
    """Return the provider's requested wait in seconds, when it sends one.

    Retry-After is a *minimum* wait. Callers must not shorten it — retrying
    early simply earns another rejection.
    """

    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None

    for header in (
        "retry-after",
        "Retry-After",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "anthropic-ratelimit-requests-reset",
    ):
        raw = headers.get(header)
        if not raw:
            continue
        seconds = parse_retry_after_value(raw)
        if seconds is not None:
            return seconds
    return None


def diagnose(exc: BaseException, status_code: Optional[int] = None) -> Diagnosis:
    """Classify an exception into an actionable diagnosis."""

    haystack = f"{extract_provider_message(exc)} {exc}".lower()

    for signature, code in _SIGNATURES:
        if signature in haystack:
            return DIAGNOSES[code]

    if status_code is not None:
        code = _STATUS_CODES.get(status_code)
        if code is not None:
            return DIAGNOSES[code]
        if 500 <= status_code < 600:
            return DIAGNOSES["provider_unavailable"]

    return DIAGNOSES["provider_error"]
