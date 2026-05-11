import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from dgentic import provider_runtime, provider_transport
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
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.body = body
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def http_error(status_code: int, headers: dict | None = None) -> HTTPError:
    return HTTPError(
        "http://127.0.0.1:1234/v1/chat/completions",
        status_code,
        "Provider failed.",
        headers or {},
        BytesIO(b'{"token":"provider-error-secret","content":"raw failure content"}'),
    )


def lm_studio_response(content: str = "Hello from LM Studio.") -> bytes:
    return json.dumps(
        {
            "id": "chatcmpl-test",
            "model": "local-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
        }
    ).encode("utf-8")


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


def test_provider_generation_retries_429_then_succeeds_without_sleep(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append({"url": request.full_url, "timeout_seconds": timeout_seconds})
        if len(calls) == 1:
            raise http_error(429, headers={"Retry-After": "2"})
        return FakeResponse(lm_studio_response("Hello after retry."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            base_url="http://127.0.0.1:1234",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert result.content == "Hello after retry."
    assert calls == [
        {"url": "http://127.0.0.1:1234/v1/chat/completions", "timeout_seconds": 60.0},
        {"url": "http://127.0.0.1:1234/v1/chat/completions", "timeout_seconds": 60.0},
    ]
    assert sleeps == [2.0]
    completion_metadata = event_log.records[-1]["metadata"]
    assert completion_metadata["attempt_count"] == 2
    assert completion_metadata["retry_count"] == 1
    assert completion_metadata["final_status_code"] == 200
    assert completion_metadata["retry_delays_seconds"] == [2.0]
    serialized_event = json.dumps(event_log.records[-1], sort_keys=True, default=str)
    assert "Hello after retry." not in serialized_event
    assert "provider-error-secret" not in serialized_event


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_provider_generation_retries_5xx_then_succeeds(status_code, monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(status_code)
        if len(calls) == 1:
            raise http_error(status_code)
        return FakeResponse(lm_studio_response("Recovered."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            base_url="http://127.0.0.1:1234",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert result.content == "Recovered."
    assert len(calls) == 2
    assert sleeps == [0.2]


def test_provider_generation_exhausted_retryable_status_raises_safe_error(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise http_error(503)

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=2),
    )

    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                base_url="http://127.0.0.1:1234",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert len(calls) == 2
    assert sleeps == [0.2]
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderRetryExhaustedError"
    assert failure_metadata["attempt_count"] == 2
    assert failure_metadata["retry_count"] == 1
    assert failure_metadata["final_status_code"] == 503
    assert failure_metadata["retry_exhausted"] is True
    serialized_event = json.dumps(event_log.records[-1], sort_keys=True, default=str)
    assert "provider-error-secret" not in serialized_event
    assert "raw failure content" not in serialized_event


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 408])
def test_provider_generation_does_not_retry_non_rate_limit_4xx(
    status_code,
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise http_error(status_code)

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)

    with pytest.raises(provider_transport.ProviderTransportError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                base_url="http://127.0.0.1:1234",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert len(calls) == 1
    assert sleeps == []
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["final_status_code"] == status_code
    assert failure_metadata["retry_count"] == 0
    assert failure_metadata["retry_exhausted"] is False


@pytest.mark.parametrize(
    ("retry_after", "expected_delay"),
    [
        ("999", 2.0),
        ("-1", 0.0),
        ("not-a-number", 0.2),
        ("NaN", 0.2),
        ("Infinity", 0.2),
        ("-Infinity", 0.2),
    ],
)
def test_provider_generation_caps_or_ignores_unsafe_retry_after_values(
    retry_after,
    expected_delay,
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(429, headers={"Retry-After": retry_after})
        return FakeResponse(lm_studio_response("Recovered after retry-after edge."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            base_url="http://127.0.0.1:1234",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert result.content == "Recovered after retry-after edge."
    assert len(calls) == 2
    assert sleeps == [expected_delay]


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
            request=Request("http://127.0.0.1:11434/api/chat"),
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

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

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
