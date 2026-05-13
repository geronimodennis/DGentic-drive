from hashlib import sha256
from time import perf_counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from dgentic.events import event_log
from dgentic.network_policy import (
    NetworkApproval,
    NetworkApprovalRequiredError,
    NetworkDomainPolicyDecision,
    NetworkDomainPolicyError,
    claim_network_approval,
    create_network_approval,
    evaluate_network_domain_policy,
    safe_network_url_for_review,
)
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType, WebRetrievalFetchResponse

WEB_RETRIEVAL_NETWORK_SURFACE = "web_retrieval"
WEB_RETRIEVAL_FETCH_ACTION = "fetch"
WEB_RETRIEVAL_ACCEPT_HEADER = (
    "text/*, application/json, application/xml, application/xhtml+xml, "
    "application/*+json, application/*+xml"
)


class WebRetrievalFetchError(OSError):
    """Raised when a guarded web retrieval fetch fails safely."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class WebRetrievalRedirectError(PermissionError):
    """Raised when an upstream response tries to redirect the guarded fetch."""


class _NoWebRetrievalRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        raise WebRetrievalRedirectError("Web retrieval redirects are blocked.")


_WEB_RETRIEVAL_OPENER = build_opener(_NoWebRetrievalRedirectHandler, ProxyHandler({}))


def evaluate_web_retrieval_network_policy(
    url: str,
    *,
    actor: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkDomainPolicyDecision:
    return evaluate_network_domain_policy(
        url,
        settings=settings,
        actor=actor,
        action=WEB_RETRIEVAL_FETCH_ACTION,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def create_web_retrieval_network_approval(
    url: str,
    *,
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkApproval:
    return create_network_approval(
        url,
        surface=WEB_RETRIEVAL_NETWORK_SURFACE,
        action=WEB_RETRIEVAL_FETCH_ACTION,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        settings=settings,
    )


def authorize_web_retrieval_network_request(
    url: str,
    *,
    approval_id: str | None = None,
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkDomainPolicyDecision:
    decision = evaluate_web_retrieval_network_policy(
        url,
        actor=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        settings=settings,
    )
    if decision.mode == "deny":
        raise PermissionError(decision.reason)
    if decision.mode == "approval_required":
        if not approval_id:
            raise NetworkApprovalRequiredError(
                "Web retrieval requires a bound network approval before fetch."
            )
        claim_network_approval(
            approval_id,
            url=url,
            surface=WEB_RETRIEVAL_NETWORK_SURFACE,
            action=WEB_RETRIEVAL_FETCH_ACTION,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
            settings=settings,
        )
    return decision


def fetch_web_retrieval_url(
    url: str,
    *,
    approval_id: str | None = None,
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    timeout_seconds: float | None = None,
    max_response_bytes: int | None = None,
    settings: Any | None = None,
) -> WebRetrievalFetchResponse:
    active_settings = settings if settings is not None else _get_settings()
    resolved_timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(active_settings.web_retrieval_timeout_seconds)
    )
    resolved_max_bytes = (
        int(max_response_bytes)
        if max_response_bytes is not None
        else int(active_settings.web_retrieval_max_response_bytes)
    )
    _validate_fetch_bounds(resolved_timeout, resolved_max_bytes)
    _validate_fetch_url(url)
    _authorize_fetch_context_or_raise(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    decision = evaluate_web_retrieval_network_policy(
        url,
        actor=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        settings=active_settings,
    )
    if decision.matched_domain is None:
        raise PermissionError("Web retrieval fetch requires an explicit network policy rule.")
    if decision.mode == "deny":
        raise PermissionError(decision.reason)
    if decision.mode == "approval_required":
        if not approval_id:
            raise NetworkApprovalRequiredError(
                "Web retrieval requires a bound network approval before fetch."
            )
        claim_network_approval(
            approval_id,
            url=url,
            surface=WEB_RETRIEVAL_NETWORK_SURFACE,
            action=WEB_RETRIEVAL_FETCH_ACTION,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
            settings=active_settings,
        )
    elif approval_id:
        raise NetworkApprovalRequiredError(
            "approval_id is only valid when web retrieval policy requires approval."
        )

    started = perf_counter()
    try:
        response = _open_web_retrieval_request(url, timeout_seconds=resolved_timeout)
        try:
            status_code = _status_code(response)
            content_type_header = _content_type_header(response)
            content_type = _normalized_content_type(content_type_header)
            if not _is_text_like_content_type(content_type):
                raise WebRetrievalFetchError(
                    "Web retrieval only supports text-like response content.",
                    status_code=415,
                )
            charset = _response_charset(response) or "utf-8"
            raw_body, truncated = _read_bounded_response(response, resolved_max_bytes)
            content_text = _decode_response_text(raw_body, charset)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except WebRetrievalRedirectError:
        raise
    except WebRetrievalFetchError:
        raise
    except HTTPError as exc:
        raise WebRetrievalFetchError(
            "Web retrieval request failed.",
            status_code=int(exc.code),
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise WebRetrievalFetchError("Web retrieval request failed.") from exc

    duration_ms = round((perf_counter() - started) * 1000, 3)
    safe_url = safe_network_url_for_review(decision.url)
    content_sha256 = sha256(raw_body).hexdigest()
    content_text = redact_sensitive_values(content_text)
    event_log.record(
        LogEventType.web_retrieval,
        "Fetched web retrieval URL.",
        actor=requested_by or "system",
        subject_id=decision.host,
        metadata={
            "url": safe_url,
            "host": decision.host,
            "status_code": status_code,
            "content_type": content_type,
            "charset": charset,
            "size_bytes": len(raw_body),
            "truncated": truncated,
            "duration_ms": duration_ms,
            "mode": decision.mode,
            "matched_domain": decision.matched_domain,
            "network_approval_id": approval_id if decision.mode == "approval_required" else None,
        },
    )
    return WebRetrievalFetchResponse(
        url=safe_url,
        host=decision.host,
        mode=decision.mode,
        matched_domain=decision.matched_domain,
        policy_reason=redact_sensitive_values(decision.reason),
        status_code=status_code,
        content_type=content_type,
        charset=charset,
        content_sha256=content_sha256,
        size_bytes=len(raw_body),
        truncated=truncated,
        content_text=content_text,
        network_approval_id=approval_id if decision.mode == "approval_required" else None,
    )


def _get_settings() -> Any:
    from dgentic.settings import get_settings

    return get_settings()


def _validate_fetch_bounds(timeout_seconds: float, max_response_bytes: int) -> None:
    if timeout_seconds < 0.1 or timeout_seconds > 30.0:
        raise ValueError("Web retrieval timeout_seconds is out of range.")
    if max_response_bytes < 1 or max_response_bytes > 2 * 1024 * 1024:
        raise ValueError("Web retrieval max_response_bytes is out of range.")


def _validate_fetch_url(url: str) -> None:
    try:
        parts = urlsplit(url.strip())
        _ = parts.port
    except ValueError as exc:
        raise NetworkDomainPolicyError("Web retrieval URL is not valid.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise NetworkDomainPolicyError("Web retrieval URL must use http or https with a host.")
    if parts.username or parts.password:
        raise NetworkDomainPolicyError("Web retrieval URL must not include credentials.")
    if parts.fragment:
        raise NetworkDomainPolicyError("Web retrieval URL must not include a fragment.")


def _authorize_fetch_context_or_raise(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> None:
    from dgentic.orchestration import (
        OrchestrationContextAuthorizationError,
        authorize_network_action,
    )

    decision = authorize_network_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    if not decision.allowed:
        raise OrchestrationContextAuthorizationError(decision.reason)


def _open_web_retrieval_request(url: str, *, timeout_seconds: float) -> Any:
    request = Request(
        url,
        method="GET",
        headers={
            "Accept": WEB_RETRIEVAL_ACCEPT_HEADER,
            "Accept-Encoding": "identity",
            "User-Agent": "DGentic-WebRetrieval/1.0",
        },
    )
    return _WEB_RETRIEVAL_OPENER.open(request, timeout=timeout_seconds)


def _read_bounded_response(response: Any, max_response_bytes: int) -> tuple[bytes, bool]:
    raw_body = response.read(max_response_bytes + 1)
    if not isinstance(raw_body, bytes):
        raw_body = bytes(raw_body)
    if len(raw_body) <= max_response_bytes:
        return raw_body, False
    return raw_body[:max_response_bytes], True


def _content_type_header(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    value = headers.get("Content-Type", "")
    return value if isinstance(value, str) else ""


def _normalized_content_type(content_type_header: str) -> str:
    return content_type_header.split(";", 1)[0].strip().lower()


def _is_text_like_content_type(content_type: str) -> bool:
    return (
        content_type.startswith("text/")
        or content_type in {"application/json", "application/xml", "application/xhtml+xml"}
        or content_type.endswith("+json")
        or content_type.endswith("+xml")
    )


def _response_charset(response: Any) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    get_content_charset = getattr(headers, "get_content_charset", None)
    if callable(get_content_charset):
        charset = get_content_charset()
        if isinstance(charset, str) and charset.strip():
            return charset.strip().lower()
    return None


def _decode_response_text(raw_body: bytes, charset: str) -> str:
    try:
        return raw_body.decode(charset, errors="replace")
    except LookupError as exc:
        raise WebRetrievalFetchError(
            "Web retrieval response charset is unsupported.",
            status_code=415,
        ) from exc


def _status_code(response: Any) -> int | None:
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
