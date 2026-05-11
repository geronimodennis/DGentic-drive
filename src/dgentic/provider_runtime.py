import json
from collections.abc import Iterator
from os import environ
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

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
from dgentic.redaction import redact_metadata
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings

DEFAULT_GENERATION_TIMEOUT_SECONDS = 60.0
OLLAMA_PROVIDER_ID = "ollama"
LM_STUDIO_PROVIDER_ID = "lm-studio"
EXTERNAL_PLACEHOLDER_PROVIDER_ID = "external-placeholder"
EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID = "external-openai-compatible"


class ProviderFeatureNotSupportedError(NotImplementedError):
    """Raised when a requested provider capability is intentionally unavailable."""


class ProviderConfigurationError(ValueError):
    """Raised when a configured provider is unavailable before transport."""


class ProviderApprovalRequiredError(PermissionError):
    """Raised when provider generation requires explicit approval."""


class ProviderChatMessage(BaseModel):
    role: str
    content: str


class ProviderGenerationRequest(BaseModel):
    provider_id: str
    model: str
    messages: list[ProviderChatMessage]
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False
    approved: bool = False
    approval_id: str | None = None
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS


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

    if request.provider_id in {OLLAMA_PROVIDER_ID, EXTERNAL_PLACEHOLDER_PROVIDER_ID}:
        raise ProviderFeatureNotSupportedError(
            "Provider streaming is not implemented for this provider."
        )

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _extract_content(provider_id: str, response: dict[str, Any]) -> str:
    if provider_id == OLLAMA_PROVIDER_ID:
        message = response.get("message", {})
        if not isinstance(message, dict):
            return ""
        return str(message.get("content", ""))

    if provider_id in {LM_STUDIO_PROVIDER_ID, EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}:
        choices = response.get("choices", [])
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return ""
        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return ""
        return str(message.get("content", ""))

    raise ValueError(f"Unsupported provider_id: {provider_id}")


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
                "model",
                "created_at",
                "done",
                "done_reason",
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            )
            if key in response
        }
        message = response.get("message")
        if isinstance(message, dict) and "role" in message:
            safe_metadata["message_role"] = message["role"]
        return redact_metadata(safe_metadata)

    if provider_id in {LM_STUDIO_PROVIDER_ID, EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}:
        choices = response.get("choices", [])
        finish_reasons = []
        if isinstance(choices, list):
            finish_reasons = [
                choice.get("finish_reason")
                for choice in choices
                if isinstance(choice, dict) and choice.get("finish_reason") is not None
            ]
        safe_metadata = {
            key: response[key]
            for key in ("id", "object", "created", "model", "usage")
            if key in response
        }
        safe_metadata["choice_count"] = len(choices) if isinstance(choices, list) else 0
        safe_metadata["finish_reasons"] = finish_reasons
        return redact_metadata(safe_metadata)

    return redact_metadata({"response_keys": sorted(str(key) for key in response)})


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
        for payload in _iter_openai_compatible_stream_payloads(transport_result):
            for event in _stream_events_from_openai_payload(
                provider_id=request.provider_id,
                model=request.model,
                payload=payload,
            ):
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


def _stream_events_from_openai_payload(
    *,
    provider_id: str,
    model: str,
    payload: dict[str, Any],
) -> Iterator[ProviderStreamEvent]:
    choices = payload.get("choices", [])
    if not isinstance(choices, list):
        raise ProviderUpstreamResponseError("Provider returned malformed streaming choices.")
    for choice in choices:
        if not isinstance(choice, dict):
            raise ProviderUpstreamResponseError("Provider returned malformed streaming choice.")
        delta_payload = choice.get("delta", {})
        delta = ""
        if isinstance(delta_payload, dict) and delta_payload.get("content") is not None:
            delta = str(delta_payload.get("content", ""))
        finish_reason = choice.get("finish_reason")
        finish_reason_text = str(finish_reason) if finish_reason is not None else None
        if delta or finish_reason_text is not None:
            yield ProviderStreamEvent(
                provider_id=provider_id,
                model=model,
                delta=delta,
                finish_reason=finish_reason_text,
                raw_response_metadata=_safe_stream_response_metadata(payload, choice),
            )


def _safe_stream_response_metadata(
    payload: dict[str, Any],
    choice: dict[str, Any],
) -> dict[str, Any]:
    safe_metadata = {
        key: payload[key] for key in ("id", "object", "created", "model", "usage") if key in payload
    }
    if choice.get("index") is not None:
        safe_metadata["choice_index"] = choice["index"]
    return redact_metadata(safe_metadata)


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
        raise ProviderApprovalRequiredError(
            "External provider approval_id execution is not implemented yet."
        )
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


__all__ = [
    "EXTERNAL_PLACEHOLDER_PROVIDER_ID",
    "EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID",
    "LM_STUDIO_PROVIDER_ID",
    "OLLAMA_PROVIDER_ID",
    "ProviderApprovalRequiredError",
    "ProviderConfigurationError",
    "ProviderEgressPolicyError",
    "ProviderFeatureNotSupportedError",
    "ProviderRateLimitError",
    "ProviderUpstreamResponseError",
    "ProviderChatMessage",
    "ProviderGenerationRequest",
    "ProviderGenerationResult",
    "ProviderStreamEvent",
    "generate_provider_completion",
    "stream_provider_completion",
]
