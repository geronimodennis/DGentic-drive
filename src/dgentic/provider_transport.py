import json
import math
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request

from dgentic.provider_policy import ProviderEgressPolicyError, open_provider_request

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_INITIAL_DELAY_SECONDS = 0.2
DEFAULT_RETRY_MAX_DELAY_SECONDS = 2.0
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 2.0


class ProviderTransportError(OSError):
    """Raised when provider transport fails without exposing response bodies."""

    def __init__(
        self,
        message: str = "Provider request failed.",
        *,
        status_code: int | None = None,
        attempt_count: int = 1,
        retry_count: int = 0,
        retryable: bool = False,
        retry_exhausted: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempt_count = attempt_count
        self.retry_count = retry_count
        self.retryable = retryable
        self.retry_exhausted = retry_exhausted
        self.retry_after_seconds = retry_after_seconds


class ProviderRetryExhaustedError(ProviderTransportError):
    """Raised when retryable provider transport failures exceed policy."""


class ProviderRateLimitError(ProviderRetryExhaustedError):
    """Raised when provider rate-limit retries are exhausted."""


class ProviderUpstreamResponseError(ProviderTransportError):
    """Raised when an upstream provider response cannot be decoded safely."""


@dataclass(frozen=True)
class ProviderRetryPolicy:
    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    initial_delay_seconds: float = DEFAULT_RETRY_INITIAL_DELAY_SECONDS
    max_delay_seconds: float = DEFAULT_RETRY_MAX_DELAY_SECONDS
    backoff_multiplier: float = DEFAULT_RETRY_BACKOFF_MULTIPLIER

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("Provider retry max_attempts must be at least 1.")
        if self.initial_delay_seconds < 0:
            raise ValueError("Provider retry initial delay must not be negative.")
        if self.max_delay_seconds < 0:
            raise ValueError("Provider retry max delay must not be negative.")
        if self.backoff_multiplier < 1:
            raise ValueError("Provider retry backoff multiplier must be at least 1.")


@dataclass(frozen=True)
class ProviderTransportRequest:
    url: str
    method: str = "GET"
    payload: dict | None = None
    timeout_seconds: float = 60.0
    headers: dict[str, str] = field(default_factory=dict)
    retry_policy: ProviderRetryPolicy = field(default_factory=ProviderRetryPolicy)


@dataclass(frozen=True)
class ProviderTransportResult:
    payload: dict
    attempt_count: int
    retry_count: int
    final_status_code: int | None = None
    retry_delays_seconds: list[float] = field(default_factory=list)


def send_provider_json_request(request: ProviderTransportRequest) -> ProviderTransportResult:
    retry_delays: list[float] = []
    for attempt_index in range(request.retry_policy.max_attempts):
        attempt_count = attempt_index + 1
        try:
            response_payload, status_code = _send_once(request)
            return ProviderTransportResult(
                payload=response_payload,
                attempt_count=attempt_count,
                retry_count=len(retry_delays),
                final_status_code=status_code,
                retry_delays_seconds=retry_delays,
            )
        except ProviderEgressPolicyError:
            raise
        except ProviderTransportError as exc:
            raise exc
        except HTTPError as exc:
            transport_error = _http_error_to_transport_error(
                exc,
                attempt_count=attempt_count,
                retry_count=len(retry_delays),
            )
        except TimeoutError as exc:
            transport_error = _generic_retryable_error(
                exc,
                attempt_count=attempt_count,
                retry_count=len(retry_delays),
            )
        except URLError as exc:
            transport_error = _generic_retryable_error(
                exc,
                attempt_count=attempt_count,
                retry_count=len(retry_delays),
            )
        except OSError as exc:
            transport_error = _generic_retryable_error(
                exc,
                attempt_count=attempt_count,
                retry_count=len(retry_delays),
            )

        if not _can_retry(transport_error, attempt_count, request.retry_policy):
            raise _final_transport_error(transport_error)

        delay_seconds = _retry_delay_seconds(
            transport_error,
            attempt_index=attempt_index,
            policy=request.retry_policy,
        )
        retry_delays.append(delay_seconds)
        sleep_provider_retry(delay_seconds)

    raise ProviderRetryExhaustedError(retry_exhausted=True)


def sleep_provider_retry(delay_seconds: float) -> None:
    time.sleep(delay_seconds)


def transport_error_metadata(exc: BaseException) -> dict:
    if not isinstance(exc, ProviderTransportError):
        return {}
    metadata = {
        "attempt_count": exc.attempt_count,
        "retry_count": exc.retry_count,
        "retryable": exc.retryable,
        "retry_exhausted": exc.retry_exhausted,
    }
    if exc.status_code is not None:
        metadata["final_status_code"] = exc.status_code
    if exc.retry_after_seconds is not None:
        metadata["retry_after_seconds"] = exc.retry_after_seconds
    return metadata


def _send_once(request: ProviderTransportRequest) -> tuple[dict, int | None]:
    http_request = _build_http_request(request)
    with open_provider_request(http_request, timeout_seconds=request.timeout_seconds) as response:
        try:
            payload = json.loads(response.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderUpstreamResponseError("Provider returned malformed JSON.") from exc
    if not isinstance(payload, dict):
        raise ProviderUpstreamResponseError("Provider returned a non-object JSON response.")
    return payload, _status_code(response)


def _build_http_request(request: ProviderTransportRequest) -> Request:
    headers = {
        "Accept": "application/json",
        **request.headers,
    }
    body = None
    if request.payload is not None:
        body = json.dumps(request.payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    return Request(
        request.url,
        data=body,
        method=request.method,
        headers=headers,
    )


def _http_error_to_transport_error(
    exc: HTTPError,
    *,
    attempt_count: int,
    retry_count: int,
) -> ProviderTransportError:
    status_code = exc.code
    retry_after_seconds = _retry_after_seconds(exc)
    retryable = status_code in RETRYABLE_STATUS_CODES
    return ProviderTransportError(
        "Provider request failed.",
        status_code=status_code,
        attempt_count=attempt_count,
        retry_count=retry_count,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
    )


def _generic_retryable_error(
    exc: OSError,
    *,
    attempt_count: int,
    retry_count: int,
) -> ProviderTransportError:
    return ProviderTransportError(
        "Provider request failed.",
        attempt_count=attempt_count,
        retry_count=retry_count,
        retryable=True,
    )


def _can_retry(
    exc: ProviderTransportError,
    attempt_count: int,
    policy: ProviderRetryPolicy,
) -> bool:
    return exc.retryable and attempt_count < policy.max_attempts


def _final_transport_error(exc: ProviderTransportError) -> ProviderTransportError:
    if exc.retryable:
        error_type = (
            ProviderRateLimitError if exc.status_code == 429 else ProviderRetryExhaustedError
        )
        return error_type(
            "Provider request failed.",
            status_code=exc.status_code,
            attempt_count=exc.attempt_count,
            retry_count=exc.retry_count,
            retryable=True,
            retry_exhausted=True,
            retry_after_seconds=exc.retry_after_seconds,
        )
    return exc


def _retry_delay_seconds(
    exc: ProviderTransportError,
    *,
    attempt_index: int,
    policy: ProviderRetryPolicy,
) -> float:
    if exc.retry_after_seconds is not None:
        return round(min(max(exc.retry_after_seconds, 0.0), policy.max_delay_seconds), 3)
    delay = policy.initial_delay_seconds * (policy.backoff_multiplier**attempt_index)
    return round(min(delay, policy.max_delay_seconds), 3)


def _retry_after_seconds(exc: HTTPError) -> float | None:
    raw_value = exc.headers.get("Retry-After") if exc.headers is not None else None
    if raw_value is None:
        return None
    try:
        retry_after_seconds = float(raw_value)
    except ValueError:
        return None
    if not math.isfinite(retry_after_seconds):
        return None
    return max(retry_after_seconds, 0.0)


def _status_code(response: object) -> int | None:
    status = getattr(response, "status", None)
    if status is not None:
        return int(status)
    code = getattr(response, "code", None)
    if code is not None:
        return int(code)
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        result = getcode()
        return int(result) if result is not None else None
    return None
