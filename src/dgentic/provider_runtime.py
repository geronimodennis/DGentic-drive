import json
from time import perf_counter
from typing import Any
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from dgentic.events import event_log
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings

DEFAULT_GENERATION_TIMEOUT_SECONDS = 60.0
OLLAMA_PROVIDER_ID = "ollama"
LM_STUDIO_PROVIDER_ID = "lm-studio"


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
        raw_response = _post_json(url, payload, request.timeout_seconds)
        duration_ms = _duration_ms(started_at)
        result = ProviderGenerationResult(
            provider_id=request.provider_id,
            model=request.model,
            content=_extract_content(request.provider_id, raw_response),
            raw_response_metadata=raw_response,
            duration_ms=duration_ms,
        )
        event_log.record(
            LogEventType.provider,
            "Completed provider generation.",
            subject_id=request.provider_id,
            metadata=result.model_dump(mode="json"),
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
                "error": str(exc),
            },
        )
        raise


def _build_provider_request(request: ProviderGenerationRequest) -> tuple[str, dict[str, Any]]:
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
        return f"{_base_url_for(request)}/v1/chat/completions", payload

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _extract_content(provider_id: str, response: dict[str, Any]) -> str:
    if provider_id == OLLAMA_PROVIDER_ID:
        message = response.get("message", {})
        return str(message.get("content", ""))

    if provider_id == LM_STUDIO_PROVIDER_ID:
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", ""))

    raise ValueError(f"Unsupported provider_id: {provider_id}")


def _base_url_for(request: ProviderGenerationRequest) -> str:
    if request.base_url:
        return request.base_url.rstrip("/")

    settings = get_settings()
    if request.provider_id == OLLAMA_PROVIDER_ID:
        return settings.ollama_base_url.rstrip("/")
    if request.provider_id == LM_STUDIO_PROVIDER_ID:
        return settings.lm_studio_base_url.rstrip("/")

    raise ValueError(f"Unsupported provider_id: {request.provider_id}")


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    http_request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urlopen(http_request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _duration_ms(started_at: float) -> int:
    return round((perf_counter() - started_at) * 1000)


__all__ = [
    "LM_STUDIO_PROVIDER_ID",
    "OLLAMA_PROVIDER_ID",
    "ProviderChatMessage",
    "ProviderGenerationRequest",
    "ProviderGenerationResult",
    "generate_provider_completion",
]
