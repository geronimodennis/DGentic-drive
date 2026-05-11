import json

import pytest

from dgentic import provider_runtime
from dgentic.provider_policy import (
    ProviderEgressPolicyError,
    _NoProviderRedirectHandler,
)
from dgentic.provider_runtime import (
    ProviderGenerationRequest,
    generate_provider_completion,
)
from dgentic.schemas import LogEventType


class RecordingEventLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(
        self,
        event_type: LogEventType,
        message: str,
        *,
        actor: str = "system",
        subject_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.records.append(
            {
                "event_type": event_type,
                "message": message,
                "actor": actor,
                "subject_id": subject_id,
                "metadata": metadata or {},
            }
        )


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_ollama_generation_posts_chat_payload_and_returns_content(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []
    raw_response = {
        "model": "llama3.1",
        "message": {"role": "assistant", "content": "Hello from Ollama."},
        "done": True,
        "total_duration": 12345,
    }

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return raw_response

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="ollama",
            model="llama3.1",
            base_url="http://127.0.0.1:11434/",
            messages=[{"role": "user", "content": "Say hello."}],
            options={"num_ctx": 4096},
            temperature=0.2,
            max_tokens=128,
            timeout_seconds=5,
        )
    )

    assert calls == [
        {
            "url": "http://127.0.0.1:11434/api/chat",
            "payload": {
                "model": "llama3.1",
                "messages": [{"role": "user", "content": "Say hello."}],
                "options": {"num_ctx": 4096, "temperature": 0.2, "num_predict": 128},
                "stream": False,
            },
            "timeout_seconds": 5,
        }
    ]
    assert result.provider_id == "ollama"
    assert result.model == "llama3.1"
    assert result.content == "Hello from Ollama."
    assert result.raw_response_metadata == {
        "model": "llama3.1",
        "done": True,
        "total_duration": 12345,
        "message_role": "assistant",
    }
    assert result.duration_ms >= 0
    assert [record["message"] for record in event_log.records] == [
        "Started provider generation.",
        "Completed provider generation.",
    ]
    assert all(record["event_type"] == LogEventType.provider for record in event_log.records)
    completion_metadata = event_log.records[-1]["metadata"]
    assert "content" not in completion_metadata
    assert completion_metadata["content_length"] == len("Hello from Ollama.")


def test_lm_studio_generation_posts_chat_completions_payload(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-test",
        "model": "local-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from LM Studio."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
        "authorization": "Bearer upstream-response-secret",
        "token": "upstream-token-secret",
    }

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return raw_response

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            base_url="http://127.0.0.1:1234",
            messages=[{"role": "user", "content": "Say hello."}],
            temperature=0.1,
            max_tokens=64,
            timeout_seconds=7,
        )
    )

    assert calls == [
        {
            "url": "http://127.0.0.1:1234/v1/chat/completions",
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "Say hello."}],
                "temperature": 0.1,
                "max_tokens": 64,
                "stream": False,
            },
            "timeout_seconds": 7,
        }
    ]
    assert result.provider_id == "lm-studio"
    assert result.model == "local-model"
    assert result.content == "Hello from LM Studio."
    assert result.raw_response_metadata == {
        "id": "chatcmpl-test",
        "model": "local-model",
        "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
        "choice_count": 1,
        "finish_reasons": ["stop"],
    }
    assert result.duration_ms >= 0
    serialized = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    assert "upstream-response-secret" not in serialized
    assert "upstream-token-secret" not in serialized
    assert "Hello from LM Studio." in serialized
    serialized_event = json.dumps(event_log.records[-1], sort_keys=True, default=str)
    assert "content" not in event_log.records[-1]["metadata"]
    assert "Hello from LM Studio." not in serialized_event
    assert "upstream-response-secret" not in serialized_event
    assert "upstream-token-secret" not in serialized_event


def test_provider_generation_rejects_disallowed_base_url_before_post(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {}

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    with pytest.raises(provider_runtime.ProviderEgressPolicyError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="ollama",
                model="llama3.1",
                base_url="http://169.254.169.254/latest",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert calls == []
    assert [record["message"] for record in event_log.records] == [
        "Started provider generation.",
        "Provider generation failed.",
    ]
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderEgressPolicyError"
    serialized_failure = json.dumps(failure_metadata, sort_keys=True)
    assert "169.254.169.254" not in serialized_failure


def test_provider_generation_rejects_unsupported_streaming_before_post(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {}

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    with pytest.raises(provider_runtime.ProviderFeatureNotSupportedError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                messages=[{"role": "user", "content": "Say hello."}],
                stream=True,
            )
        )

    assert calls == []
    assert event_log.records[-1]["metadata"]["error_type"] == "ProviderFeatureNotSupportedError"


def test_external_placeholder_generation_is_not_implemented(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {}

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    with pytest.raises(provider_runtime.ProviderFeatureNotSupportedError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="external-placeholder",
                model="external-default",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert calls == []
    assert event_log.records[-1]["metadata"]["error_type"] == "ProviderFeatureNotSupportedError"


def test_provider_http_redirects_are_blocked_by_policy() -> None:
    handler = _NoProviderRedirectHandler()

    with pytest.raises(ProviderEgressPolicyError, match="redirects are blocked"):
        handler.redirect_request(
            request=provider_runtime.Request("http://127.0.0.1:11434/api/chat"),
            file_pointer=None,
            code=302,
            message="Found",
            headers={"Location": "http://example.com/redirected"},
            new_url="http://example.com/redirected",
        )


def test_provider_post_json_wraps_malformed_upstream_json(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float) -> FakeResponse:
        calls.append({"url": request.full_url, "timeout_seconds": timeout_seconds})
        return FakeResponse(b'{"not": "valid"')

    monkeypatch.setattr(provider_runtime, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderUpstreamResponseError):
        provider_runtime._post_json(
            "http://127.0.0.1:1234/v1/chat/completions",
            {"model": "local-model"},
            5,
        )

    assert calls == [{"url": "http://127.0.0.1:1234/v1/chat/completions", "timeout_seconds": 5}]


def test_unsupported_provider_logs_failure(monkeypatch) -> None:
    event_log = RecordingEventLog()
    monkeypatch.setattr(provider_runtime, "event_log", event_log)

    with pytest.raises(ValueError, match="Unsupported provider_id: unknown"):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="unknown",
                model="local-model",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert [record["message"] for record in event_log.records] == [
        "Started provider generation.",
        "Provider generation failed.",
    ]
    assert event_log.records[-1]["metadata"]["error_type"] == "ValueError"
