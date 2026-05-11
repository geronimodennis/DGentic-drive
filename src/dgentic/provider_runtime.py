import hashlib
import hmac
import json
import math
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from os import environ
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from dgentic.events import event_log
from dgentic.provider_policy import (
    ProviderEgressPolicyError,
    allowed_provider_base_urls_for_provider,
    normalize_provider_base_url,
)
from dgentic.provider_transport import (
    ProviderRateLimitError,
    ProviderRetryPolicy,
    ProviderStreamingTransportResult,
    ProviderTransportRequest,
    ProviderTransportResult,
    ProviderUpstreamResponseError,
    open_provider_stream_request,
    send_provider_json_request,
    transport_error_metadata,
)
from dgentic.redaction import redact_metadata, redact_sensitive_values
from dgentic.schemas import LogEventType, PermissionMode
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

DEFAULT_GENERATION_TIMEOUT_SECONDS = 60.0
DEFAULT_PROVIDER_APPROVAL_TTL_MINUTES = 30
MAX_PROVIDER_MESSAGES = 64
MAX_PROVIDER_MESSAGE_CONTENT_CHARS = 100_000
MAX_PROVIDER_OPTIONS = 32
MAX_PROVIDER_OPTION_KEY_CHARS = 96
MAX_PROVIDER_OPTIONS_JSON_CHARS = 16_384
MAX_PROVIDER_OPTION_DEPTH = 6
MAX_PROVIDER_OPTION_LIST_ITEMS = 128
MAX_PROVIDER_TIMEOUT_SECONDS = 600.0
MAX_PROVIDER_TOKENS = 200_000
MAX_PROVIDER_CONTEXT_FIELD_CHARS = 256
MAX_PROVIDER_METADATA_ABS_NUMERIC = 10**18
SUPPORTED_PROVIDER_MESSAGE_ROLES = {
    "assistant",
    "developer",
    "system",
    "tool",
    "user",
}
SAFE_PROVIDER_FINISH_REASONS = {
    "content_filter",
    "function_call",
    "length",
    "load",
    "stop",
    "tool_calls",
    "unload",
}
SAFE_PROVIDER_USAGE_KEYS = {
    "completion_tokens",
    "eval_count",
    "eval_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "prompt_tokens",
    "total_duration",
    "total_tokens",
}
OLLAMA_PROVIDER_ID = "ollama"
LM_STUDIO_PROVIDER_ID = "lm-studio"
EXTERNAL_PLACEHOLDER_PROVIDER_ID = "external-placeholder"
EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID = "external-openai-compatible"
PROVIDER_APPROVAL_DIGEST_PREFIX = "hmac-sha256:"
REDACTED_LEGACY_DIGEST_MARKER = "[LEGACY_DIGEST_REDACTED]"
_PROVIDER_APPROVAL_DIGEST_KEY_FILE = "provider-approval-digest.key"
_PROVIDER_APPROVAL_DIGEST_LOCK = Lock()
_provider_approval_lock = Lock()


class ProviderFeatureNotSupportedError(NotImplementedError):
    """Raised when a requested provider capability is intentionally unavailable."""


class ProviderConfigurationError(ValueError):
    """Raised when a configured provider is unavailable before transport."""


class ProviderApprovalRequiredError(PermissionError):
    """Raised when provider generation requires explicit approval."""


class ProviderApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    executed = "executed"


class ProviderChatMessage(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=MAX_PROVIDER_MESSAGE_CONTENT_CHARS)

    @field_validator("role")
    @classmethod
    def role_must_be_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_PROVIDER_MESSAGE_ROLES:
            allowed_roles = ", ".join(sorted(SUPPORTED_PROVIDER_MESSAGE_ROLES))
            raise ValueError(f"Provider message role must be one of: {allowed_roles}.")
        return normalized

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Provider message content must not be blank.")
        return value


class ProviderGenerationRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    messages: list[ProviderChatMessage] = Field(
        min_length=1,
        max_length=MAX_PROVIDER_MESSAGES,
    )
    base_url: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=MAX_PROVIDER_TOKENS)
    options: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False
    approved: bool = False
    approval_id: str | None = Field(default=None, max_length=MAX_PROVIDER_CONTEXT_FIELD_CHARS)
    requested_by: str | None = Field(default=None, max_length=MAX_PROVIDER_CONTEXT_FIELD_CHARS)
    agent_id: str | None = Field(default=None, max_length=MAX_PROVIDER_CONTEXT_FIELD_CHARS)
    agent_role: str | None = Field(default=None, max_length=MAX_PROVIDER_CONTEXT_FIELD_CHARS)
    task_id: str | None = Field(default=None, max_length=MAX_PROVIDER_CONTEXT_FIELD_CHARS)
    timeout_seconds: float = Field(
        default=DEFAULT_GENERATION_TIMEOUT_SECONDS,
        gt=0.0,
        le=MAX_PROVIDER_TIMEOUT_SECONDS,
    )

    @field_validator("provider_id", "model")
    @classmethod
    def text_identifiers_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Provider request identifiers must not be blank.")
        return stripped

    @field_validator("options")
    @classmethod
    def options_must_be_bounded_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_provider_options(value)
        return value


class ProviderApproval(BaseModel):
    id: str
    provider_id: str
    model: str
    stream: bool = False
    message_count: int = 0
    review_messages: list[dict[str, Any]] = Field(default_factory=list)
    option_keys: list[str] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float
    permission_mode: PermissionMode = PermissionMode.approval_required
    message_digest: str = ""
    options_digest: str = ""
    base_url_digest: str = ""
    credential_env_digest: str = ""
    model_allowlist_digest: str = ""
    approval_digest: str = ""
    status: ProviderApprovalStatus = ProviderApprovalStatus.pending
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: (
            datetime.now(UTC) + timedelta(minutes=DEFAULT_PROVIDER_APPROVAL_TTL_MINUTES)
        )
    )
    decided_at: datetime | None = None
    executed_at: datetime | None = None

    def model_post_init(self, __context: object) -> None:
        self.review_messages = redact_metadata(self.review_messages)
        self.requested_by = _redact_optional_sensitive_text(self.requested_by)
        self.agent_id = _redact_optional_sensitive_text(self.agent_id)
        self.agent_role = _redact_optional_sensitive_text(self.agent_role)
        self.task_id = _redact_optional_sensitive_text(self.task_id)
        self.decided_by = _redact_optional_sensitive_text(self.decided_by)
        self.decision_reason = _redact_optional_sensitive_text(self.decision_reason)
        self.denial_reason = _redact_optional_sensitive_text(self.denial_reason)
        self.message_digest = _sanitize_provider_approval_digest(self.message_digest)
        self.options_digest = _sanitize_provider_approval_digest(self.options_digest)
        self.base_url_digest = _sanitize_provider_approval_digest(self.base_url_digest)
        self.credential_env_digest = _sanitize_provider_approval_digest(self.credential_env_digest)
        self.model_allowlist_digest = _sanitize_provider_approval_digest(
            self.model_allowlist_digest
        )
        self.approval_digest = _sanitize_provider_approval_digest(self.approval_digest)


class ProviderApprovalReview(BaseModel):
    id: str
    status: ProviderApprovalStatus
    provider_id: str
    model: str
    stream: bool
    message_count: int
    review_messages: list[dict[str, Any]] = Field(default_factory=list)
    option_keys: list[str] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float
    permission_mode: PermissionMode
    message_digest: str = ""
    options_digest: str = ""
    base_url_digest: str = ""
    credential_env_digest: str = ""
    model_allowlist_digest: str = ""
    approval_digest: str = ""
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    requires_bound_execution_request: bool = True
    direct_execute_available: bool = False
    review_warnings: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    executed_at: datetime | None = None


class ProviderGenerationResult(BaseModel):
    provider_id: str
    model: str
    content: str
    raw_response_metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int


class ProviderStreamEvent(BaseModel):
    provider_id: str
    model: str
    event: str = "chunk"
    delta: str = ""
    finish_reason: str | None = None
    raw_response_metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = None
    error: str | None = None


_provider_approvals = JsonCollection("provider-approvals", ProviderApproval)


def create_provider_approval(
    provider_id: str,
    request: ProviderGenerationRequest,
    *,
    requested_by: str | None = None,
) -> ProviderApproval:
    request = _provider_request_for_path(provider_id, request)
    if provider_id != EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID:
        raise ValueError("Only approval-required external provider requests can be queued.")

    settings = get_settings()
    _reject_external_runtime_base_url(request)
    _validate_external_model(request.model, settings)
    base_url = _external_base_url(settings)
    _external_headers(settings)
    credential_env = settings.external_openai_compatible_api_key_env.strip()
    model_allowlist = _external_models(settings)
    requested_by_value = requested_by or request.requested_by

    message_digest = provider_messages_digest(request.messages)
    options_digest = provider_generation_options_digest(request)
    base_url_digest = _provider_hmac_digest(_canonical_json(base_url))
    credential_env_digest = _provider_hmac_digest(_canonical_json(credential_env))
    model_allowlist_digest = _provider_hmac_digest(_canonical_json(sorted(model_allowlist)))
    approval_digest = provider_approval_digest(
        provider_id=request.provider_id,
        model=request.model,
        stream=request.stream,
        message_digest=message_digest,
        options_digest=options_digest,
        base_url_digest=base_url_digest,
        credential_env_digest=credential_env_digest,
        model_allowlist_digest=model_allowlist_digest,
        timeout_seconds=request.timeout_seconds,
        requested_by=requested_by_value,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        permission_mode=PermissionMode.approval_required,
    )
    approval = ProviderApproval(
        id=f"provider-approval-{uuid4()}",
        provider_id=request.provider_id,
        model=request.model,
        stream=request.stream,
        message_count=len(request.messages),
        review_messages=_provider_review_messages(request.messages),
        option_keys=sorted(str(key) for key in request.options),
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        timeout_seconds=request.timeout_seconds,
        permission_mode=PermissionMode.approval_required,
        message_digest=message_digest,
        options_digest=options_digest,
        base_url_digest=base_url_digest,
        credential_env_digest=credential_env_digest,
        model_allowlist_digest=model_allowlist_digest,
        approval_digest=approval_digest,
        requested_by=requested_by_value,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )
    _provider_approvals.upsert(approval)
    event_log.record(
        LogEventType.approval,
        "Created provider approval request.",
        subject_id=approval.id,
        metadata={
            "provider_id": approval.provider_id,
            "model": approval.model,
            "stream": approval.stream,
            "message_count": approval.message_count,
            "option_keys": approval.option_keys,
            "permission_mode": approval.permission_mode,
            "requested_by": approval.requested_by,
            "agent_id": approval.agent_id,
            "agent_role": approval.agent_role,
            "task_id": approval.task_id,
            "message_digest": approval.message_digest,
            "options_digest": approval.options_digest,
            "base_url_digest": approval.base_url_digest,
            "credential_env_digest": approval.credential_env_digest,
            "model_allowlist_digest": approval.model_allowlist_digest,
            "approval_digest": approval.approval_digest,
            "expires_at": approval.expires_at.isoformat(),
        },
    )
    return approval


def list_provider_approvals(
    status: ProviderApprovalStatus | str | None = None,
) -> list[ProviderApproval]:
    approvals = _provider_approvals.list()
    if status is None:
        return approvals
    requested_status = ProviderApprovalStatus(status)
    return [approval for approval in approvals if approval.status == requested_status]


def get_provider_approval_review(approval_id: str) -> ProviderApprovalReview:
    approval = _get_provider_approval_or_raise(approval_id)
    warnings = [
        "Provider approval stores request digests and safe message metadata; execute with "
        "a bound request that resubmits the same provider payload."
    ]
    if _provider_approval_is_expired(approval):
        warnings.append("Approval is expired.")
    return ProviderApprovalReview(
        id=approval.id,
        status=approval.status,
        provider_id=approval.provider_id,
        model=approval.model,
        stream=approval.stream,
        message_count=approval.message_count,
        review_messages=approval.review_messages,
        option_keys=approval.option_keys,
        temperature=approval.temperature,
        max_tokens=approval.max_tokens,
        timeout_seconds=approval.timeout_seconds,
        permission_mode=approval.permission_mode,
        message_digest=approval.message_digest,
        options_digest=approval.options_digest,
        base_url_digest=approval.base_url_digest,
        credential_env_digest=approval.credential_env_digest,
        model_allowlist_digest=approval.model_allowlist_digest,
        approval_digest=approval.approval_digest,
        requested_by=approval.requested_by,
        agent_id=approval.agent_id,
        agent_role=approval.agent_role,
        task_id=approval.task_id,
        direct_execute_available=False,
        review_warnings=warnings,
        decided_by=approval.decided_by,
        decision_reason=_redact_optional_sensitive_text(approval.decision_reason),
        denial_reason=_redact_optional_sensitive_text(approval.denial_reason),
        created_at=approval.created_at,
        updated_at=approval.updated_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        executed_at=approval.executed_at,
    )


def approve_provider_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> ProviderApproval:
    redacted_reason = _redact_optional_sensitive_text(reason)

    def approve(current: ProviderApproval) -> ProviderApproval:
        if current.status != ProviderApprovalStatus.pending:
            raise ValueError(
                "Only pending provider approvals can be approved; "
                f"current status is {current.status}."
            )
        if _provider_approval_is_expired(current):
            raise ValueError(f"Provider approval {approval_id} has expired and cannot be approved.")

        now = datetime.now(UTC)
        current.status = ProviderApprovalStatus.approved
        current.decided_by = _redact_optional_sensitive_text(decided_by)
        current.decision_reason = redacted_reason
        current.decided_at = now
        current.updated_at = now
        return current

    approval = _provider_approvals.update(approval_id, approve)
    event_log.record(
        LogEventType.approval,
        "Approved provider request.",
        subject_id=approval.id,
        actor=approval.decided_by or "system",
        metadata={
            "provider_id": approval.provider_id,
            "model": approval.model,
            "stream": approval.stream,
            **({"reason": redacted_reason} if redacted_reason else {}),
        },
    )
    return approval


def deny_provider_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> ProviderApproval:
    redacted_reason = _redact_optional_sensitive_text(reason)

    def deny(current: ProviderApproval) -> ProviderApproval:
        if current.status != ProviderApprovalStatus.pending:
            raise ValueError(
                "Only pending provider approvals can be denied; "
                f"current status is {current.status}."
            )

        now = datetime.now(UTC)
        current.status = ProviderApprovalStatus.denied
        current.decided_by = _redact_optional_sensitive_text(decided_by)
        current.decision_reason = redacted_reason
        current.denial_reason = redacted_reason
        current.decided_at = now
        current.updated_at = now
        return current

    approval = _provider_approvals.update(approval_id, deny)
    event_log.record(
        LogEventType.approval,
        "Denied provider request.",
        subject_id=approval.id,
        actor=approval.decided_by or "system",
        metadata={
            "provider_id": approval.provider_id,
            "model": approval.model,
            "stream": approval.stream,
            **({"reason": redacted_reason} if redacted_reason else {}),
        },
    )
    return approval


def generate_provider_completion(
    request: ProviderGenerationRequest,
) -> ProviderGenerationResult:
    started_at = perf_counter()
    event_log.record(
        LogEventType.provider,
        "Started provider generation.",
        subject_id=request.provider_id,
        metadata={
            "provider_id": request.provider_id,
            "model": request.model,
            "message_count": len(request.messages),
        },
    )

    try:
        url, payload, headers = _build_provider_request(request)
        if headers:
            transport_result = _post_json(
                url,
                payload,
                request.timeout_seconds,
                headers=headers,
            )
        else:
            transport_result = _post_json(url, payload, request.timeout_seconds)
        raw_response, retry_metadata = _transport_payload_and_metadata(transport_result)
        duration_ms = _duration_ms(started_at)
        result = ProviderGenerationResult(
            provider_id=request.provider_id,
            model=request.model,
            content=_extract_content(request.provider_id, raw_response),
            raw_response_metadata=_safe_response_metadata(request.provider_id, raw_response),
            duration_ms=duration_ms,
        )
        event_log.record(
            LogEventType.provider,
            "Completed provider generation.",
            subject_id=request.provider_id,
            metadata=_completion_event_metadata(result, retry_metadata=retry_metadata),
        )
        return result
    except Exception as exc:
        event_log.record(
            LogEventType.provider,
            "Provider generation failed.",
            subject_id=request.provider_id,
            metadata={
                "provider_id": request.provider_id,
                "model": request.model,
                "duration_ms": _duration_ms(started_at),
                "error_type": type(exc).__name__,
                "error": _safe_error_message(exc),
                **transport_error_metadata(exc),
            },
        )
        raise


def stream_provider_completion(
    request: ProviderGenerationRequest,
) -> Iterator[ProviderStreamEvent]:
    request = request.model_copy(update={"stream": True})
    started_at = perf_counter()
    event_log.record(
        LogEventType.provider,
        "Started provider streaming generation.",
        subject_id=request.provider_id,
        metadata={
            "provider_id": request.provider_id,
            "model": request.model,
            "message_count": len(request.messages),
        },
    )

    try:
        url, payload, headers = _build_provider_stream_request(request)
        transport_result = _open_stream(
            url,
            payload,
            request.timeout_seconds,
            headers=headers,
        )
        return _iter_provider_stream_events(request, started_at, transport_result)
    except Exception as exc:
        event_log.record(
            LogEventType.provider,
            "Provider streaming generation failed.",
            subject_id=request.provider_id,
            metadata={
                "provider_id": request.provider_id,
                "model": request.model,
                "duration_ms": _duration_ms(started_at),
                "error_type": type(exc).__name__,
                "error": _safe_error_message(exc),
                **transport_error_metadata(exc),
            },
        )
        raise


def _build_provider_request(
    request: ProviderGenerationRequest,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    if request.stream:
        raise ProviderFeatureNotSupportedError(
            "Provider streaming is not implemented for this endpoint."
        )

    messages = [message.model_dump(mode="json") for message in request.messages]

    if request.provider_id == OLLAMA_PROVIDER_ID:
        options = dict(request.options)
        if request.temperature is not None:
            options.setdefault("temperature", request.temperature)
        if request.max_tokens is not None:
            options.setdefault("num_predict", request.max_tokens)
        return (
            f"{_base_url_for(request)}/api/chat",
            {
                "model": request.model,
                "messages": messages,
                "options": options,
                "stream": False,
            },
            {},
        )

    if request.provider_id == LM_STUDIO_PROVIDER_ID:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        payload["stream"] = False
        return f"{_base_url_for(request)}/v1/chat/completions", payload, {}

    if request.provider_id == EXTERNAL_PLACEHOLDER_PROVIDER_ID:
        raise ProviderFeatureNotSupportedError("External provider adapter is not implemented yet.")

    if request.provider_id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID:
        settings = get_settings()
        _reject_external_runtime_base_url(request)
        _authorize_external_provider_request(request, settings=settings)
        _validate_external_model(request.model, settings)
        base_url = _external_base_url(settings)
        headers = _external_headers(settings)
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return (
            f"{base_url}/chat/completions",
            payload,
            headers,
        )

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _build_provider_stream_request(
    request: ProviderGenerationRequest,
) -> tuple[str, dict[str, Any], dict[str, str]]:
    messages = [message.model_dump(mode="json") for message in request.messages]

    if request.provider_id == OLLAMA_PROVIDER_ID:
        options = dict(request.options)
        if request.temperature is not None:
            options.setdefault("temperature", request.temperature)
        if request.max_tokens is not None:
            options.setdefault("num_predict", request.max_tokens)
        return (
            f"{_base_url_for(request)}/api/chat",
            {
                "model": request.model,
                "messages": messages,
                "options": options,
                "stream": True,
            },
            {"Accept": "application/x-ndjson"},
        )

    if request.provider_id == LM_STUDIO_PROVIDER_ID:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return f"{_base_url_for(request)}/v1/chat/completions", payload, {}

    if request.provider_id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID:
        settings = get_settings()
        _reject_external_runtime_base_url(request)
        _authorize_external_provider_request(request, settings=settings)
        _validate_external_model(request.model, settings)
        base_url = _external_base_url(settings)
        headers = _external_headers(settings)
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        return f"{base_url}/chat/completions", payload, headers

    if request.provider_id == EXTERNAL_PLACEHOLDER_PROVIDER_ID:
        raise ProviderFeatureNotSupportedError(
            "Provider streaming is not implemented for this provider."
        )

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _extract_content(provider_id: str, response: dict[str, Any]) -> str:
    if provider_id == OLLAMA_PROVIDER_ID:
        _raise_if_provider_error_response(response)
        message = response.get("message", {})
        if not isinstance(message, dict):
            raise ProviderUpstreamResponseError("Provider returned malformed chat message.")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderUpstreamResponseError("Provider returned malformed chat content.")
        return content

    if provider_id in {LM_STUDIO_PROVIDER_ID, EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}:
        _raise_if_provider_error_response(response)
        choices = response.get("choices", [])
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderUpstreamResponseError("Provider returned malformed chat choices.")
        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            raise ProviderUpstreamResponseError("Provider returned malformed chat message.")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderUpstreamResponseError("Provider returned malformed chat content.")
        return content

    raise ValueError(f"Unsupported provider_id: {provider_id}")


def _raise_if_provider_error_response(response: dict[str, Any]) -> None:
    if response.get("error") is not None:
        raise ProviderUpstreamResponseError("Provider returned an error response.")


def _validate_provider_options(options: dict[str, Any]) -> None:
    _validate_provider_option_mapping(options, depth=0)
    try:
        encoded = json.dumps(
            options,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Provider options must be JSON-compatible.") from exc
    if len(encoded) > MAX_PROVIDER_OPTIONS_JSON_CHARS:
        raise ValueError(
            f"Provider options JSON must be at most {MAX_PROVIDER_OPTIONS_JSON_CHARS} characters."
        )


def _validate_provider_option_mapping(options: dict[Any, Any], *, depth: int) -> None:
    if depth > MAX_PROVIDER_OPTION_DEPTH:
        raise ValueError(
            f"Provider options may be nested at most {MAX_PROVIDER_OPTION_DEPTH} levels."
        )
    if len(options) > MAX_PROVIDER_OPTIONS:
        raise ValueError(f"Provider options must include at most {MAX_PROVIDER_OPTIONS} keys.")
    for key, value in options.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Provider option keys must be non-empty strings.")
        if len(key) > MAX_PROVIDER_OPTION_KEY_CHARS:
            raise ValueError(
                f"Provider option keys must be at most {MAX_PROVIDER_OPTION_KEY_CHARS} characters."
            )
        _validate_provider_option_value(value, depth=depth + 1)


def _validate_provider_option_value(value: Any, *, depth: int) -> None:
    if depth > MAX_PROVIDER_OPTION_DEPTH:
        raise ValueError(
            f"Provider options may be nested at most {MAX_PROVIDER_OPTION_DEPTH} levels."
        )
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Provider numeric option values must be finite.")
        return
    if isinstance(value, list):
        if len(value) > MAX_PROVIDER_OPTION_LIST_ITEMS:
            raise ValueError(
                "Provider option lists must include at most "
                f"{MAX_PROVIDER_OPTION_LIST_ITEMS} items."
            )
        for item in value:
            _validate_provider_option_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        _validate_provider_option_mapping(value, depth=depth)
        return
    raise ValueError("Provider options must contain only JSON-compatible values.")


def _base_url_for(request: ProviderGenerationRequest) -> str:
    settings = get_settings()
    if request.provider_id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID and request.base_url:
        _reject_external_runtime_base_url(request)
    if request.base_url:
        return _validate_base_url_for_provider(
            provider_id=request.provider_id,
            base_url=request.base_url,
            settings=settings,
        )

    if request.provider_id == OLLAMA_PROVIDER_ID:
        return _validate_base_url_for_provider(
            provider_id=request.provider_id,
            base_url=settings.ollama_base_url,
            settings=settings,
        )
    if request.provider_id == LM_STUDIO_PROVIDER_ID:
        return _validate_base_url_for_provider(
            provider_id=request.provider_id,
            base_url=settings.lm_studio_base_url,
            settings=settings,
        )
    if request.provider_id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID:
        return _external_base_url(settings)

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _safe_response_metadata(provider_id: str, response: dict[str, Any]) -> dict[str, Any]:
    if provider_id == OLLAMA_PROVIDER_ID:
        safe_metadata = {
            key: response[key]
            for key in (
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            )
            if key in response and _is_safe_provider_numeric_value(response[key])
        }
        if isinstance(response.get("done"), bool):
            safe_metadata["done"] = response["done"]
        done_reason = _safe_provider_finish_reason(response.get("done_reason"))
        if done_reason is not None:
            safe_metadata["done_reason"] = done_reason
        message = response.get("message")
        message_role = _safe_provider_message_role(
            message.get("role") if isinstance(message, dict) else None
        )
        if message_role is not None:
            safe_metadata["message_role"] = message_role
        return safe_metadata

    if provider_id in {LM_STUDIO_PROVIDER_ID, EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}:
        choices = response.get("choices", [])
        finish_reasons = []
        if isinstance(choices, list):
            finish_reasons = [
                safe_reason
                for choice in choices
                if isinstance(choice, dict)
                for safe_reason in [_safe_provider_finish_reason(choice.get("finish_reason"))]
                if safe_reason is not None
            ]
        safe_metadata = {}
        usage = _safe_provider_usage(response.get("usage"))
        if usage:
            safe_metadata["usage"] = usage
        safe_metadata["choice_count"] = len(choices) if isinstance(choices, list) else 0
        safe_metadata["finish_reasons"] = finish_reasons
        return safe_metadata

    return redact_metadata({"response_keys": sorted(str(key) for key in response)})


def _safe_provider_usage(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if str(key) in SAFE_PROVIDER_USAGE_KEYS and _is_safe_provider_numeric_value(item)
    }


def _safe_provider_finish_reason(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in SAFE_PROVIDER_FINISH_REASONS:
        return normalized
    return "other"


def _safe_provider_message_role(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in SUPPORTED_PROVIDER_MESSAGE_ROLES else None


def _is_safe_provider_numeric_value(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if isinstance(value, int):
        return abs(value) <= MAX_PROVIDER_METADATA_ABS_NUMERIC
    return math.isfinite(value) and abs(value) <= MAX_PROVIDER_METADATA_ABS_NUMERIC


def _completion_event_metadata(
    result: ProviderGenerationResult,
    *,
    retry_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider_id": result.provider_id,
        "model": result.model,
        "duration_ms": result.duration_ms,
        "content_length": len(result.content),
        "raw_response_metadata": result.raw_response_metadata,
        **retry_metadata,
    }


def _safe_error_message(exc: Exception) -> str:
    if isinstance(
        exc,
        (ProviderEgressPolicyError, ProviderFeatureNotSupportedError, ValueError),
    ):
        return str(exc)
    return "Provider request failed."


def _post_json(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    *,
    headers: dict[str, str] | None = None,
) -> ProviderTransportResult:
    return send_provider_json_request(
        ProviderTransportRequest(
            url=url,
            method="POST",
            payload=payload,
            timeout_seconds=timeout_seconds,
            headers=headers or {},
            retry_policy=_generation_retry_policy(),
        )
    )


def _open_stream(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    *,
    headers: dict[str, str] | None = None,
) -> ProviderStreamingTransportResult:
    stream_headers = {"Accept": "text/event-stream", **(headers or {})}
    return open_provider_stream_request(
        ProviderTransportRequest(
            url=url,
            method="POST",
            payload=payload,
            timeout_seconds=timeout_seconds,
            headers=stream_headers,
            retry_policy=_generation_retry_policy(),
        )
    )


def _iter_provider_stream_events(
    request: ProviderGenerationRequest,
    started_at: float,
    transport_result: ProviderStreamingTransportResult,
) -> Iterator[ProviderStreamEvent]:
    chunk_count = 0
    content_length = 0
    finish_reasons: list[str] = []
    try:
        for event in _stream_events_for_provider(request, transport_result):
            chunk_count += 1
            content_length += len(event.delta)
            if event.finish_reason is not None:
                finish_reasons.append(event.finish_reason)
            yield event
        event_log.record(
            LogEventType.provider,
            "Completed provider streaming generation.",
            subject_id=request.provider_id,
            metadata={
                "provider_id": request.provider_id,
                "model": request.model,
                "duration_ms": _duration_ms(started_at),
                "chunk_count": chunk_count,
                "content_length": content_length,
                "finish_reasons": finish_reasons,
                **_stream_transport_metadata(transport_result),
            },
        )
    except Exception as exc:
        event_log.record(
            LogEventType.provider,
            "Provider streaming generation failed.",
            subject_id=request.provider_id,
            metadata={
                "provider_id": request.provider_id,
                "model": request.model,
                "duration_ms": _duration_ms(started_at),
                "chunk_count": chunk_count,
                "content_length": content_length,
                "error_type": type(exc).__name__,
                "error": _safe_error_message(exc),
                **_stream_transport_metadata(transport_result),
                **transport_error_metadata(exc),
            },
        )
        if chunk_count == 0:
            raise
        yield ProviderStreamEvent(
            provider_id=request.provider_id,
            model=request.model,
            event="error",
            error=_safe_error_message(exc),
            duration_ms=_duration_ms(started_at),
        )


def _stream_events_for_provider(
    request: ProviderGenerationRequest,
    transport_result: ProviderStreamingTransportResult,
) -> Iterator[ProviderStreamEvent]:
    if request.provider_id == OLLAMA_PROVIDER_ID:
        for payload in _iter_ollama_stream_payloads(transport_result):
            event = _stream_event_from_ollama_payload(
                provider_id=request.provider_id,
                model=request.model,
                payload=payload,
            )
            if event is not None:
                yield event
        return

    for payload in _iter_openai_compatible_stream_payloads(transport_result):
        yield from _stream_events_from_openai_payload(
            provider_id=request.provider_id,
            model=request.model,
            payload=payload,
        )


def _iter_ollama_stream_payloads(
    transport_result: ProviderStreamingTransportResult,
) -> Iterator[dict[str, Any]]:
    for line in transport_result.iter_lines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ProviderUpstreamResponseError(
                "Provider returned malformed streaming data."
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderUpstreamResponseError(
                "Provider returned a non-object streaming response."
            )
        yield payload


def _iter_openai_compatible_stream_payloads(
    transport_result: ProviderStreamingTransportResult,
) -> Iterator[dict[str, Any]]:
    for line in transport_result.iter_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            continue
        if not stripped.startswith("data:"):
            continue
        data = stripped.removeprefix("data:").strip()
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProviderUpstreamResponseError(
                "Provider returned malformed streaming data."
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderUpstreamResponseError(
                "Provider returned a non-object streaming response."
            )
        yield payload


def _stream_event_from_ollama_payload(
    *,
    provider_id: str,
    model: str,
    payload: dict[str, Any],
) -> ProviderStreamEvent | None:
    _raise_if_provider_error_response(payload)
    message = payload.get("message", {})
    if message is not None and not isinstance(message, dict):
        raise ProviderUpstreamResponseError("Provider returned malformed streaming message.")
    delta = ""
    if isinstance(message, dict) and message.get("content") is not None:
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderUpstreamResponseError("Provider returned malformed streaming content.")
        delta = content
    done = payload.get("done") is True
    finish_reason = _safe_provider_finish_reason(payload.get("done_reason"))
    if not delta and not done and finish_reason is None:
        return None
    return ProviderStreamEvent(
        provider_id=provider_id,
        model=model,
        delta=delta,
        finish_reason=finish_reason,
        raw_response_metadata=_safe_ollama_stream_response_metadata(payload),
    )


def _stream_events_from_openai_payload(
    *,
    provider_id: str,
    model: str,
    payload: dict[str, Any],
) -> Iterator[ProviderStreamEvent]:
    _raise_if_provider_error_response(payload)
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        raise ProviderUpstreamResponseError("Provider returned malformed streaming choices.")
    for choice in choices:
        if not isinstance(choice, dict):
            raise ProviderUpstreamResponseError("Provider returned malformed streaming choice.")
        delta_payload = choice.get("delta", {})
        if delta_payload is not None and not isinstance(delta_payload, dict):
            raise ProviderUpstreamResponseError("Provider returned malformed streaming delta.")
        delta = ""
        if isinstance(delta_payload, dict) and delta_payload.get("content") is not None:
            content = delta_payload.get("content")
            if not isinstance(content, str):
                raise ProviderUpstreamResponseError(
                    "Provider returned malformed streaming content."
                )
            delta = content
        finish_reason = choice.get("finish_reason")
        finish_reason_text = _safe_provider_finish_reason(finish_reason)
        if delta or finish_reason_text is not None:
            yield ProviderStreamEvent(
                provider_id=provider_id,
                model=model,
                delta=delta,
                finish_reason=finish_reason_text,
                raw_response_metadata=_safe_stream_response_metadata(payload, choice),
            )


def _safe_ollama_stream_response_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    safe_metadata = {
        key: payload[key]
        for key in (
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
        )
        if key in payload and _is_safe_provider_numeric_value(payload[key])
    }
    if isinstance(payload.get("done"), bool):
        safe_metadata["done"] = payload["done"]
    done_reason = _safe_provider_finish_reason(payload.get("done_reason"))
    if done_reason is not None:
        safe_metadata["done_reason"] = done_reason
    message = payload.get("message")
    message_role = _safe_provider_message_role(
        message.get("role") if isinstance(message, dict) else None
    )
    if message_role is not None:
        safe_metadata["message_role"] = message_role
    return safe_metadata


def _safe_stream_response_metadata(
    payload: dict[str, Any],
    choice: dict[str, Any],
) -> dict[str, Any]:
    safe_metadata: dict[str, Any] = {}
    usage = _safe_provider_usage(payload.get("usage"))
    if usage:
        safe_metadata["usage"] = usage
    choice_index = choice.get("index")
    if _is_safe_provider_numeric_value(choice_index):
        safe_metadata["choice_index"] = choice_index
    return safe_metadata


def _stream_transport_metadata(
    transport_result: ProviderStreamingTransportResult,
) -> dict[str, Any]:
    return {
        "attempt_count": transport_result.attempt_count,
        "retry_count": transport_result.retry_count,
        "final_status_code": transport_result.final_status_code,
        "retry_delays_seconds": transport_result.retry_delays_seconds,
    }


def _generation_retry_policy() -> ProviderRetryPolicy:
    settings = get_settings()
    return ProviderRetryPolicy(
        max_attempts=settings.provider_retry_max_attempts,
        initial_delay_seconds=settings.provider_retry_initial_delay_seconds,
        max_delay_seconds=settings.provider_retry_max_delay_seconds,
        backoff_multiplier=settings.provider_retry_backoff_multiplier,
    )


def _transport_payload_and_metadata(
    transport_result: ProviderTransportResult | dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(transport_result, ProviderTransportResult):
        return (
            transport_result.payload,
            {
                "attempt_count": transport_result.attempt_count,
                "retry_count": transport_result.retry_count,
                "final_status_code": transport_result.final_status_code,
                "retry_delays_seconds": transport_result.retry_delays_seconds,
            },
        )
    return transport_result, {
        "attempt_count": 1,
        "retry_count": 0,
        "final_status_code": None,
        "retry_delays_seconds": [],
    }


def _duration_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)


def _external_base_url(settings: Any) -> str:
    if not settings.external_openai_compatible_base_url.strip():
        raise ProviderConfigurationError("External provider is not configured.")
    normalized = _validate_base_url_for_provider(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        base_url=settings.external_openai_compatible_base_url,
        settings=settings,
    )
    if not normalized.startswith("https://"):
        raise ProviderEgressPolicyError(
            "External provider base_url must use https when bearer credentials are configured."
        )
    return normalized


def _external_headers(settings: Any) -> dict[str, str]:
    credential_env = settings.external_openai_compatible_api_key_env.strip()
    if not credential_env:
        raise ProviderConfigurationError("External provider is not configured.")
    credential_value = environ.get(credential_env, "").strip()
    if not credential_value:
        raise ProviderConfigurationError("External provider is not configured.")
    return {"Authorization": f"Bearer {credential_value}"}


def _external_models(settings: Any) -> list[str]:
    return [
        model_name.strip()
        for model_name in settings.external_openai_compatible_models.split(",")
        if model_name.strip()
    ]


def _validate_external_model(model: str, settings: Any) -> None:
    configured_models = _external_models(settings)
    if not configured_models:
        raise ProviderConfigurationError("External provider is not configured.")
    if model not in configured_models:
        raise ValueError("External provider model is not configured.")


def _authorize_external_provider_request(
    request: ProviderGenerationRequest,
    *,
    settings: Any,
) -> None:
    if request.approval_id:
        try:
            approval = _get_provider_approval_or_raise(request.approval_id)
        except KeyError as exc:
            raise ProviderApprovalRequiredError(str(exc)) from exc
        _claim_bound_provider_approval(
            approval,
            request=request,
            settings=settings,
        )
        return
    if request.approved and settings.environment.strip().lower() in {
        "development",
        "test",
        "testing",
    }:
        return
    if request.approved:
        raise ProviderApprovalRequiredError(
            "External provider requires an approved approval_id before generation; "
            "the approved boolean bypass is only allowed in development/test mode."
        )
    raise ProviderApprovalRequiredError("External provider requires explicit approval.")


def _reject_external_runtime_base_url(request: ProviderGenerationRequest) -> None:
    if request.base_url:
        raise ProviderEgressPolicyError(
            "External provider base_url must be configured by the operator."
        )


def _validate_base_url_for_provider(*, provider_id: str, base_url: str, settings: Any) -> str:
    normalized = normalize_provider_base_url(base_url)
    if normalized not in allowed_provider_base_urls_for_provider(provider_id, settings):
        raise ProviderEgressPolicyError(
            f"Provider base_url for {provider_id} is not allowed by egress policy."
        )
    return normalized


def _provider_request_for_path(
    provider_id: str,
    request: ProviderGenerationRequest,
) -> ProviderGenerationRequest:
    if request.provider_id != provider_id:
        raise ValueError("Provider approval path provider_id must match the request provider_id.")
    return request


def _claim_bound_provider_approval(
    approval: ProviderApproval,
    *,
    request: ProviderGenerationRequest,
    settings: Any,
) -> None:
    def claim(current: ProviderApproval) -> ProviderApproval:
        _validate_bound_provider_approval(current, request=request, settings=settings)
        now = datetime.now(UTC)
        current.status = ProviderApprovalStatus.executed
        current.executed_at = now
        current.updated_at = now
        return current

    with _provider_approval_lock:
        try:
            _provider_approvals.update(approval.id, claim)
        except KeyError as exc:
            raise ProviderApprovalRequiredError(str(exc)) from exc
    event_log.record(
        LogEventType.approval,
        "Claimed provider approval for execution.",
        subject_id=approval.id,
        metadata={
            "provider_id": approval.provider_id,
            "model": approval.model,
            "stream": approval.stream,
        },
    )


def _validate_bound_provider_approval(
    approval: ProviderApproval,
    *,
    request: ProviderGenerationRequest,
    settings: Any,
) -> None:
    if approval.status != ProviderApprovalStatus.approved:
        raise ProviderApprovalRequiredError(
            f"Provider approval {approval.id} is not executable; current status is "
            f"{approval.status}."
        )
    if _provider_approval_is_expired(approval):
        raise ProviderApprovalRequiredError(
            f"Provider approval {approval.id} has expired and cannot be executed."
        )

    _reject_external_runtime_base_url(request)
    _validate_external_model(request.model, settings)
    base_url = _external_base_url(settings)
    _external_headers(settings)
    credential_env = settings.external_openai_compatible_api_key_env.strip()
    model_allowlist = _external_models(settings)
    message_digest = provider_messages_digest(request.messages)
    options_digest = provider_generation_options_digest(request)
    base_url_digest = _provider_hmac_digest(_canonical_json(base_url))
    credential_env_digest = _provider_hmac_digest(_canonical_json(credential_env))
    model_allowlist_digest = _provider_hmac_digest(_canonical_json(sorted(model_allowlist)))
    expected_approval_digest = provider_approval_digest(
        provider_id=request.provider_id,
        model=request.model,
        stream=request.stream,
        message_digest=message_digest,
        options_digest=options_digest,
        base_url_digest=base_url_digest,
        credential_env_digest=credential_env_digest,
        model_allowlist_digest=model_allowlist_digest,
        timeout_seconds=request.timeout_seconds,
        requested_by=request.requested_by,
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
        permission_mode=PermissionMode.approval_required,
    )
    checks = [
        approval.provider_id == request.provider_id,
        approval.model == request.model,
        approval.stream == request.stream,
        approval.message_count == len(request.messages),
        approval.option_keys == sorted(str(key) for key in request.options),
        approval.temperature == request.temperature,
        approval.max_tokens == request.max_tokens,
        approval.timeout_seconds == request.timeout_seconds,
        approval.permission_mode == PermissionMode.approval_required,
        approval.message_digest == message_digest,
        approval.options_digest == options_digest,
        approval.base_url_digest == base_url_digest,
        approval.credential_env_digest == credential_env_digest,
        approval.model_allowlist_digest == model_allowlist_digest,
        approval.approval_digest == expected_approval_digest,
        approval.requested_by == _redact_optional_sensitive_text(request.requested_by),
        approval.agent_id == _redact_optional_sensitive_text(request.agent_id),
        approval.agent_role == _redact_optional_sensitive_text(request.agent_role),
        approval.task_id == _redact_optional_sensitive_text(request.task_id),
    ]
    if not all(checks):
        raise ProviderApprovalRequiredError(
            f"Provider approval {approval.id} is not bound to this provider request."
        )


def _provider_approval_is_expired(approval: ProviderApproval) -> bool:
    return approval.expires_at <= datetime.now(UTC)


def _get_provider_approval_or_raise(approval_id: str) -> ProviderApproval:
    approval = _provider_approvals.get(approval_id)
    if approval is None:
        raise KeyError(f"Provider approval not found: {approval_id}")
    return approval


def _redact_optional_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    return redact_sensitive_values(text)


def _provider_approval_digest_key() -> bytes:
    settings = get_settings()
    configured_key = settings.approval_digest_key.strip()
    if configured_key:
        return configured_key.encode("utf-8")

    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = settings.root_dir / data_dir
    key_path = data_dir / _PROVIDER_APPROVAL_DIGEST_KEY_FILE
    with _PROVIDER_APPROVAL_DIGEST_LOCK:
        if key_path.exists():
            stored_key = key_path.read_text(encoding="utf-8").strip()
            if stored_key:
                return stored_key.encode("utf-8")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        generated_key = secrets.token_hex(32)
        key_path.write_text(generated_key + "\n", encoding="utf-8")
        return generated_key.encode("utf-8")


def _provider_hmac_digest(encoded_payload: str) -> str:
    digest = hmac.new(
        _provider_approval_digest_key(),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{PROVIDER_APPROVAL_DIGEST_PREFIX}{digest}"


def _sanitize_provider_approval_digest(digest: str) -> str:
    if not digest:
        return ""
    if digest.startswith(PROVIDER_APPROVAL_DIGEST_PREFIX):
        return digest
    return REDACTED_LEGACY_DIGEST_MARKER


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def provider_messages_digest(messages: list[ProviderChatMessage]) -> str:
    payload = [message.model_dump(mode="json") for message in messages]
    return _provider_hmac_digest(_canonical_json(payload))


def provider_generation_options_digest(request: ProviderGenerationRequest) -> str:
    payload = {
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "options": request.options,
    }
    return _provider_hmac_digest(_canonical_json(payload))


def provider_approval_digest(
    *,
    provider_id: str,
    model: str,
    stream: bool,
    message_digest: str,
    options_digest: str,
    base_url_digest: str,
    credential_env_digest: str,
    model_allowlist_digest: str,
    timeout_seconds: float,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    permission_mode: PermissionMode,
) -> str:
    payload = {
        "provider_id": provider_id,
        "model": model,
        "stream": stream,
        "message_digest": message_digest,
        "options_digest": options_digest,
        "base_url_digest": base_url_digest,
        "credential_env_digest": credential_env_digest,
        "model_allowlist_digest": model_allowlist_digest,
        "timeout_seconds": timeout_seconds,
        "requested_by": requested_by,
        "agent_id": agent_id,
        "agent_role": agent_role,
        "task_id": task_id,
        "permission_mode": permission_mode,
    }
    return _provider_hmac_digest(_canonical_json(payload))


def _provider_review_messages(
    messages: list[ProviderChatMessage],
) -> list[dict[str, Any]]:
    return [
        {
            "role": redact_sensitive_values(message.role),
            "content_length": len(message.content),
        }
        for message in messages
    ]


__all__ = [
    "EXTERNAL_PLACEHOLDER_PROVIDER_ID",
    "EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID",
    "LM_STUDIO_PROVIDER_ID",
    "OLLAMA_PROVIDER_ID",
    "ProviderApproval",
    "ProviderApprovalRequiredError",
    "ProviderApprovalReview",
    "ProviderApprovalStatus",
    "ProviderConfigurationError",
    "ProviderEgressPolicyError",
    "ProviderFeatureNotSupportedError",
    "ProviderRateLimitError",
    "ProviderUpstreamResponseError",
    "ProviderChatMessage",
    "ProviderGenerationRequest",
    "ProviderGenerationResult",
    "ProviderStreamEvent",
    "approve_provider_approval",
    "create_provider_approval",
    "deny_provider_approval",
    "generate_provider_completion",
    "get_provider_approval_review",
    "list_provider_approvals",
    "provider_approval_digest",
    "provider_generation_options_digest",
    "provider_messages_digest",
    "stream_provider_completion",
]
