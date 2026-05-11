from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from dgentic.events import event_log
from dgentic.provider_policy import ProviderEgressPolicyError, validate_provider_base_url
from dgentic.provider_transport import (
    ProviderRateLimitError,
    ProviderRetryPolicy,
    ProviderTransportRequest,
    ProviderTransportResult,
    ProviderUpstreamResponseError,
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


class ProviderFeatureNotSupportedError(NotImplementedError):
    """Raised when a requested provider capability is intentionally unavailable."""


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
    timeout_seconds: float = DEFAULT_GENERATION_TIMEOUT_SECONDS


class ProviderGenerationResult(BaseModel):
    provider_id: str
    model: str
    content: str
    raw_response_metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int


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
        url, payload = _build_provider_request(request)
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


def _build_provider_request(request: ProviderGenerationRequest) -> tuple[str, dict[str, Any]]:
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
        return f"{_base_url_for(request)}/v1/chat/completions", payload

    if request.provider_id == EXTERNAL_PLACEHOLDER_PROVIDER_ID:
        raise ProviderFeatureNotSupportedError("External provider adapter is not implemented yet.")

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _extract_content(provider_id: str, response: dict[str, Any]) -> str:
    if provider_id == OLLAMA_PROVIDER_ID:
        message = response.get("message", {})
        if not isinstance(message, dict):
            return ""
        return str(message.get("content", ""))

    if provider_id == LM_STUDIO_PROVIDER_ID:
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
    if request.base_url:
        return validate_provider_base_url(
            provider_id=request.provider_id,
            base_url=request.base_url,
            settings=settings,
        )

    if request.provider_id == OLLAMA_PROVIDER_ID:
        return validate_provider_base_url(
            provider_id=request.provider_id,
            base_url=settings.ollama_base_url,
            settings=settings,
        )
    if request.provider_id == LM_STUDIO_PROVIDER_ID:
        return validate_provider_base_url(
            provider_id=request.provider_id,
            base_url=settings.lm_studio_base_url,
            settings=settings,
        )

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

    if provider_id == LM_STUDIO_PROVIDER_ID:
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
) -> ProviderTransportResult:
    return send_provider_json_request(
        ProviderTransportRequest(
            url=url,
            method="POST",
            payload=payload,
            timeout_seconds=timeout_seconds,
            retry_policy=_generation_retry_policy(),
        )
    )


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


__all__ = [
    "EXTERNAL_PLACEHOLDER_PROVIDER_ID",
    "LM_STUDIO_PROVIDER_ID",
    "OLLAMA_PROVIDER_ID",
    "ProviderEgressPolicyError",
    "ProviderFeatureNotSupportedError",
    "ProviderRateLimitError",
    "ProviderUpstreamResponseError",
    "ProviderChatMessage",
    "ProviderGenerationRequest",
    "ProviderGenerationResult",
    "generate_provider_completion",
]
