"""Small, dependency-free HTTP client for P1.6 vendor connectors.

The client centralizes timeouts, bounded retries, rate-limit handling, and safe
request diagnostics.  Authorization values are sent to vendors but are never
included in traces or exception messages.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple


class ConnectorError(Exception):
    """Base error for authentication, transport, and live-sync failures."""


class ConfigurationError(ConnectorError):
    """Required local configuration is missing or unsafe."""


class ApiRequestError(ConnectorError):
    """A vendor request failed after applying the configured retry policy."""

    def __init__(self, method: str, safe_url: str, status: Optional[int], message: str) -> None:
        self.method = method
        self.safe_url = safe_url
        self.status = status
        super().__init__("%s %s failed%s: %s" % (
            method,
            safe_url,
            " with HTTP %s" % status if status is not None else "",
            message,
        ))


@dataclass(frozen=True)
class RetryPolicy:
    """Bound retry attempts and exponential delay for transient failures."""

    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def delay(self, attempt: int, retry_after: Optional[str], random_value: float) -> float:
        """Return a capped Retry-After or exponential-backoff delay."""
        if retry_after:
            try:
                return min(self.max_delay_seconds, max(0.0, float(retry_after)))
            except ValueError:
                pass
        exponential = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt - 1)))
        jitter = exponential * self.jitter_ratio * random_value
        return min(self.max_delay_seconds, exponential + jitter)


@dataclass(frozen=True)
class HttpResponse:
    """Transport-neutral HTTP response used by real and mocked clients."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    """Minimal interface that lets CI replace the network with scripted replies."""

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: float,
    ) -> HttpResponse:
        """Send one HTTP request and return its status, headers, and bytes."""


class UrllibTransport:
    """Use Python's standard-library HTTPS stack for live API calls."""

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Optional[bytes],
        timeout: float,
    ) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(response.status, dict(response.headers.items()), response.read())
        except urllib.error.HTTPError as exc:
            # HTTP errors still carry useful status, headers, and a vendor response.
            return HttpResponse(exc.code, dict(exc.headers.items()), exc.read())


@dataclass(frozen=True)
class RequestTrace:
    """Credential-free evidence about one API attempt."""

    method: str
    url: str
    status: Optional[int]
    attempt: int


class JsonHttpClient:
    """Send JSON requests with safe diagnostics and bounded transient retries."""

    TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        transport: Optional[HttpTransport] = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_seconds: float = 20.0,
        sleep: Callable[[float], None] = time.sleep,
        random_source: Callable[[], float] = random.random,
        trace: Optional[Callable[[RequestTrace], None]] = None,
    ) -> None:
        self.transport = transport or UrllibTransport()
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self.sleep = sleep
        self.random_source = random_source
        self.trace = trace

    @staticmethod
    def _safe_headers(headers: Mapping[str, str]) -> Dict[str, str]:
        """Return only non-secret headers for diagnostics."""
        blocked = {"authorization", "cookie", "set-cookie", "x-api-key"}
        return {key: value for key, value in headers.items() if key.casefold() not in blocked}

    @staticmethod
    def _error_message(body: bytes) -> str:
        """Extract a short vendor message without echoing request credentials."""
        if not body:
            return "empty response"
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "non-JSON response"
        if isinstance(parsed, Mapping):
            for key in ("message", "error_description", "error", "status"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:500]
        return "vendor returned an error response"

    @staticmethod
    def _redact(message: str, headers: Mapping[str, str], form: Optional[Mapping[str, str]]) -> str:
        """Remove request credentials if a vendor happens to echo them."""
        secrets_to_hide = []
        for key, value in headers.items():
            if key.casefold() in {"authorization", "cookie", "x-api-key"}:
                secrets_to_hide.append(value)
                if value.casefold().startswith("bearer "):
                    secrets_to_hide.append(value[7:])
        for key, value in (form or {}).items():
            if any(part in key.casefold() for part in ("token", "secret", "code")):
                secrets_to_hide.append(value)
        redacted = message
        for value in secrets_to_hide:
            if value:
                redacted = redacted.replace(value, "[REDACTED]")
        return redacted

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        document: Optional[Mapping[str, Any]] = None,
        form: Optional[Mapping[str, str]] = None,
        safe_to_retry: bool = False,
        expected_statuses: Tuple[int, ...] = (200,),
    ) -> Any:
        """Return parsed JSON or raise a redacted, actionable connector error.

        Callers must explicitly mark POST or PATCH requests safe to retry. Read
        requests are retried automatically because repeating them cannot create a
        second vendor record.
        """
        normalized_method = method.upper()
        request_headers: Dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "sai-revenueos-p1.6/1.0",
            **dict(headers or {}),
        }
        if document is not None and form is not None:
            raise ValueError("document and form are mutually exclusive")
        body: Optional[bytes] = None
        if document is not None:
            body = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form is not None:
            from urllib.parse import urlencode

            body = urlencode(form).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        may_retry = normalized_method in {"GET", "HEAD"} or safe_to_retry
        last_status: Optional[int] = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                response = self.transport.request(
                    normalized_method, url, request_headers, body, self.timeout_seconds
                )
                last_status = response.status
            except (OSError, TimeoutError) as exc:
                if self.trace:
                    self.trace(RequestTrace(normalized_method, url, None, attempt))
                if not may_retry or attempt == self.retry_policy.max_attempts:
                    raise ApiRequestError(normalized_method, url, None, type(exc).__name__) from exc
                self.sleep(self.retry_policy.delay(attempt, None, self.random_source()))
                continue

            if self.trace:
                self.trace(RequestTrace(normalized_method, url, response.status, attempt))
            if response.status in expected_statuses:
                if not response.body:
                    return {}
                try:
                    return json.loads(response.body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ApiRequestError(normalized_method, url, response.status, "invalid JSON response") from exc

            transient = response.status in self.TRANSIENT_STATUSES
            if transient and may_retry and attempt < self.retry_policy.max_attempts:
                retry_after = None
                for key, value in response.headers.items():
                    if key.casefold() == "retry-after":
                        retry_after = value
                        break
                self.sleep(self.retry_policy.delay(attempt, retry_after, self.random_source()))
                continue
            raise ApiRequestError(
                normalized_method,
                url,
                response.status,
                self._redact(self._error_message(response.body), request_headers, form),
            )
        raise ApiRequestError(normalized_method, url, last_status, "retry attempts exhausted")
