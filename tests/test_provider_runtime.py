import json
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from pydantic import ValidationError

from dgentic import provider_runtime, provider_transport
from dgentic.credentials import (
    CredentialReferenceRequest,
    CredentialResolutionError,
    create_credential_reference,
    credential_secret_for_reference,
    revoke_credential_reference,
)
from dgentic.provider_policy import (
    ProviderEgressPolicyError,
    _NoProviderRedirectHandler,
    allowed_provider_base_urls,
    validate_provider_base_url,
)
from dgentic.provider_runtime import (
    EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
    ProviderGenerationRequest,
    generate_provider_completion,
)
from dgentic.providers import default_providers
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings


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


class FakeStreamResponse:
    status = 200

    def __init__(self, lines: list[str]) -> None:
        self.lines = [line.encode("utf-8") for line in lines]
        self.closed = False

    def readline(self) -> bytes:
        if not self.lines:
            return b""
        return self.lines.pop(0)

    def close(self) -> None:
        self.closed = True


class BlockingCredentialEnviron:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, key: str, default: str | None = None) -> str | None:
        self.calls.append(key)
        raise AssertionError("credential lookup should not happen")


class TrackingCredentialEnviron:
    def __init__(self, *, key: str, value: str) -> None:
        self.key = key
        self.value = value
        self.calls: list[str] = []

    def get(self, key: str, default: str | None = None) -> str | None:
        self.calls.append(key)
        return self.value if key == self.key else default


def write_process_credential_adapter(tmp_path, body: str) -> tuple[str, Path]:
    marker_path = tmp_path / "process-credential-calls.txt"
    script_path = tmp_path / "process_credential_adapter.py"
    script_path.write_text(body, encoding="utf-8")
    return str(script_path), marker_path


@pytest.fixture(autouse=True)
def reset_provider_circuit_state():
    provider_runtime.reset_provider_circuit_state()
    yield
    provider_runtime.reset_provider_circuit_state()


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


def openai_stream_lines(
    *chunks: dict,
    done: bool = True,
) -> list[str]:
    lines = [f"data: {json.dumps(chunk)}\n" for chunk in chunks]
    if done:
        lines.append("data: [DONE]\n")
    return lines


def configure_external_provider(
    monkeypatch,
    *,
    base_url: str = "https://provider.example.test/v1",
    api_key_env: str = "DGENTIC_TEST_EXTERNAL_API_KEY",
    api_key: str = "external-api-key-secret",
    models: str = "gpt-test,gpt-other",
) -> None:
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", base_url)
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", api_key_env)
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", models)
    monkeypatch.setenv(api_key_env, api_key)
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "payload_override",
    [
        {"provider_id": "   "},
        {"model": "   "},
        {"messages": []},
        {"messages": [{"role": "invalid", "content": "Say hello."}]},
        {"messages": [{"role": "   ", "content": "Say hello."}]},
        {"messages": [{"role": "user", "content": "   "}]},
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"max_tokens": 0},
        {"timeout_seconds": 0},
        {"options": {f"key_{index}": index for index in range(33)}},
        {"options": {"bad": float("nan")}},
        {"options": {"bad": object()}},
    ],
)
def test_provider_generation_request_rejects_invalid_payload_shape(
    payload_override,
) -> None:
    payload = {
        "provider_id": "ollama",
        "model": "llama3.1",
        "messages": [{"role": "user", "content": "Say hello."}],
    }
    payload.update(payload_override)

    with pytest.raises(ValidationError):
        ProviderGenerationRequest(**payload)


def test_ollama_generation_posts_chat_payload_and_returns_content(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []
    raw_response = {
        "model": "llama3.1",
        "message": {"role": "assistant", "content": "Hello from Ollama."},
        "done": True,
        "total_duration": 12345,
        "prompt_eval_count": 8,
        "eval_count": 5,
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
    assert result.usage_metadata == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert result.estimated_cost_usd == 0.0
    assert result.raw_response_metadata == {
        "done": True,
        "total_duration": 12345,
        "prompt_eval_count": 8,
        "eval_count": 5,
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
    assert completion_metadata["usage_metadata"] == result.usage_metadata
    assert completion_metadata["estimated_cost_usd"] == 0.0


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
    assert result.usage_metadata == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert result.estimated_cost_usd == 0.0
    assert result.raw_response_metadata == {
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
    assert event_log.records[-1]["metadata"]["usage_metadata"] == result.usage_metadata
    assert event_log.records[-1]["metadata"]["estimated_cost_usd"] == 0.0
    assert "Hello from LM Studio." not in serialized_event
    assert "upstream-response-secret" not in serialized_event
    assert "upstream-token-secret" not in serialized_event


@pytest.mark.parametrize(
    ("provider_id", "base_url", "raw_response"),
    [
        (
            "ollama",
            "http://127.0.0.1:11434",
            {"error": "ollama-upstream-error-secret"},
        ),
        (
            "ollama",
            "http://127.0.0.1:11434",
            {"message": {"role": "assistant"}},
        ),
        (
            "lm-studio",
            "http://127.0.0.1:1234",
            {"choices": []},
        ),
        (
            "lm-studio",
            "http://127.0.0.1:1234",
            {"choices": [{"message": {"role": "assistant", "content": 42}}]},
        ),
        (
            "lm-studio",
            "http://127.0.0.1:1234",
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hello."},
                        "finish_reason": "secret-finish-reason",
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "eval_count": 10**309,
                    "load_duration": -1,
                    "prompt": "usage-secret",
                    "total_tokens": "usage-total-secret",
                },
                "id": "upstream-id-secret",
                "model": "upstream-model-secret",
            },
        ),
    ],
)
def test_provider_generation_handles_malformed_or_untrusted_success_payloads(
    provider_id,
    base_url,
    raw_response,
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()
    calls: list[str] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append(url)
        return raw_response

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    first_choice = (
        raw_response.get("choices", [{}])[0]
        if isinstance(raw_response.get("choices"), list) and raw_response.get("choices")
        else {}
    )
    first_message = first_choice.get("message", {}) if isinstance(first_choice, dict) else {}
    expected_error = (
        "error" in raw_response
        or provider_id == "ollama"
        or raw_response.get("choices") == []
        or not isinstance(first_message.get("content"), str)
    )
    if expected_error:
        with pytest.raises(provider_transport.ProviderUpstreamResponseError):
            generate_provider_completion(
                ProviderGenerationRequest(
                    provider_id=provider_id,
                    model="local-model",
                    base_url=base_url,
                    messages=[{"role": "user", "content": "prompt-secret-123"}],
                )
            )
        failure_metadata = event_log.records[-1]["metadata"]
        assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
        assert failure_metadata["error"] == "Provider request failed."
    else:
        result = generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=provider_id,
                model="local-model",
                base_url=base_url,
                messages=[{"role": "user", "content": "prompt-secret-123"}],
            )
        )
        assert result.raw_response_metadata == {
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            "choice_count": 1,
            "finish_reasons": ["other"],
        }

    assert len(calls) == 1
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "prompt-secret-123" not in serialized
    assert "ollama-upstream-error-secret" not in serialized
    assert "openai-compatible-upstream-error-secret" not in serialized
    assert "usage-secret" not in serialized
    assert "upstream-id-secret" not in serialized
    assert "upstream-model-secret" not in serialized


@pytest.mark.parametrize("environment", ["development", "test", "testing"])
def test_external_openai_compatible_generation_posts_authorized_chat_completion(
    environment,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", environment)
    configure_external_provider(monkeypatch)
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.headers),
                "payload": json.loads(request.data.decode("utf-8")),
                "timeout_seconds": timeout_seconds,
            }
        )
        return FakeResponse(lm_studio_response("Hello from external."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            model="gpt-test",
            messages=[{"role": "user", "content": "Say hello."}],
            temperature=0.2,
            max_tokens=128,
            approved=True,
        )
    )

    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer external-api-key-secret",
                "Content-type": "application/json",
            },
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "Say hello."}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 128,
            },
            "timeout_seconds": 60.0,
        }
    ]
    assert result.provider_id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    assert result.content == "Hello from external."
    assert result.usage_metadata == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert result.estimated_cost_usd == 0.01
    assert result.raw_response_metadata["usage"] == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    serialized = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    serialized_event = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "external-api-key-secret" not in serialized
    assert "external-api-key-secret" not in serialized_event
    assert "Hello from external." not in serialized_event
    get_settings.cache_clear()


def test_external_generation_uses_configured_model_pricing(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "test")
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": 0.5,
                        "completion_usd_per_1k_tokens": 1.0,
                        "request_estimate_usd": 0.02,
                    }
                }
            }
        ),
    )
    configure_external_provider(monkeypatch)
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeResponse(lm_studio_response("Hello with priced usage."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            model="gpt-test",
            messages=[{"role": "user", "content": "Say hello."}],
            approved=True,
        )
    )

    assert result.usage_metadata == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert result.estimated_cost_usd == 0.009
    assert event_log.records[-1]["metadata"]["estimated_cost_usd"] == 0.009
    assert "Hello with priced usage." not in json.dumps(event_log.records, default=str)
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "catalog",
    [
        "not-json",
        json.dumps(
            {
                EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": -0.1,
                        "completion_usd_per_1k_tokens": 1.0,
                    }
                }
            }
        ),
        json.dumps(
            {
                EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {"prompt_usd_per_1k_tokens": 0.5}
                }
            }
        ),
        (
            '{"external-openai-compatible":{"gpt-test":'
            '{"prompt_usd_per_1k_tokens":Infinity,'
            '"completion_usd_per_1k_tokens":1.0}}}'
        ),
    ],
)
def test_external_generation_rejects_invalid_pricing_before_transport(
    catalog,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "test")
    monkeypatch.setenv("DGENTIC_PROVIDER_PRICING_CATALOG", catalog)
    configure_external_provider(monkeypatch)
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderConfigurationError, match="pricing catalog"):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )

    assert calls == []
    get_settings.cache_clear()


def test_external_generation_requires_approval_before_transport(monkeypatch) -> None:
    configure_external_provider(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello. TOKEN=prompt-secret"}],
            )
        )

    assert calls == []
    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_streaming_requires_approval_before_credential_lookup(monkeypatch) -> None:
    configure_external_provider(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                    model="gpt-test",
                    messages=[{"role": "user", "content": "Stream hello. TOKEN=prompt-secret"}],
                )
            )
        )

    assert calls == []
    assert blocked_credentials.calls == []
    get_settings.cache_clear()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_external_generation_rejects_approved_boolean_outside_development(
    environment,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", environment)
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError, match="approval_id"):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )

    assert calls == []
    assert blocked_credentials.calls == []
    get_settings.cache_clear()


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_external_streaming_rejects_approved_boolean_before_credential_lookup(
    environment,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", environment)
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError, match="approval_id"):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                    model="gpt-test",
                    messages=[{"role": "user", "content": "Stream hello."}],
                    approved=True,
                )
            )
        )

    assert calls == []
    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_generation_accepts_bound_approval_id_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider(monkeypatch)
    tracked_credentials = TrackingCredentialEnviron(
        key="DGENTIC_TEST_EXTERNAL_API_KEY",
        value="external-api-key-secret",
    )
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "payload": json.loads(request.data.decode("utf-8")),
                "timeout_seconds": timeout_seconds,
            }
        )
        return FakeResponse(lm_studio_response("Hello from approved external."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", tracked_credentials)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello. API_KEY=prompt-secret"}],
        temperature=0.2,
        max_tokens=128,
        options={"top_p": 0.9},
        requested_by="operator TOKEN=requester-secret",
        agent_id="agent PASSWORD=agent-secret",
        agent_role="developer SECRET=role-secret",
        task_id="sprint-12 API_KEY=task-secret",
    )

    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    review = provider_runtime.get_provider_approval_review(approval.id)
    approval_storage = (tmp_path / "state" / "provider-approvals.json").read_text(encoding="utf-8")

    assert approval.status == provider_runtime.ProviderApprovalStatus.pending
    assert review.review_messages == [{"role": "user", "content_length": 32}]
    assert review.requires_bound_execution_request is True
    assert review.direct_execute_available is False
    assert "prompt-secret" not in approval_storage
    assert "requester-secret" not in approval_storage
    assert "agent-secret" not in approval_storage
    assert "role-secret" not in approval_storage
    assert "task-secret" not in approval_storage

    provider_runtime.approve_provider_approval(
        approval.id,
        decided_by="reviewer TOKEN=reviewer-secret",
        reason="approved TOKEN=reason-secret",
    )
    result = generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))

    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "Say hello. API_KEY=prompt-secret"}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 128,
            },
            "timeout_seconds": 60.0,
        }
    ]
    assert result.content == "Hello from approved external."
    executed = provider_runtime.list_provider_approvals()[0]
    assert executed.status == provider_runtime.ProviderApprovalStatus.executed
    assert executed.executed_at is not None
    assert tracked_credentials.calls == ["DGENTIC_TEST_EXTERNAL_API_KEY"]

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError, match="not executable"):
        generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))

    serialized_events = json.dumps(event_log.records, sort_keys=True, default=str)
    approval_storage = (tmp_path / "state" / "provider-approvals.json").read_text(encoding="utf-8")
    assert "external-api-key-secret" not in serialized_events
    assert "Hello from approved external." not in serialized_events
    assert "reviewer-secret" not in approval_storage
    assert "reason-secret" not in approval_storage
    get_settings.cache_clear()


def test_external_generation_uses_configured_credential_reference(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            env_var="DGENTIC_REF_EXTERNAL_API_KEY",
            label="external provider",
        )
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()
    tracked_credentials = TrackingCredentialEnviron(
        key="DGENTIC_REF_EXTERNAL_API_KEY",
        value="external-reference-secret",
    )
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "timeout_seconds": timeout_seconds,
            }
        )
        return FakeResponse(lm_studio_response("Hello from referenced credential."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", tracked_credentials)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
        requested_by="operator",
    )
    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(approval.id, decided_by="reviewer")

    result = generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))
    approval_storage = (tmp_path / "state" / "provider-approvals.json").read_text(encoding="utf-8")
    credential_storage = (tmp_path / "state" / "credential-references.json").read_text(
        encoding="utf-8"
    )
    serialized_event = json.dumps(event_log.records, sort_keys=True, default=str)

    assert result.content == "Hello from referenced credential."
    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-reference-secret",
            "timeout_seconds": 60.0,
        }
    ]
    assert tracked_credentials.calls == ["DGENTIC_REF_EXTERNAL_API_KEY"]
    assert "external-reference-secret" not in approval_storage
    assert "external-reference-secret" not in credential_storage
    assert "external-reference-secret" not in serialized_event
    get_settings.cache_clear()


def test_env_credential_reference_respects_explicit_sanitized_environ(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_REF_EXTERNAL_API_KEY", "host-secret")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            env_var="DGENTIC_REF_EXTERNAL_API_KEY",
            label="external provider",
        )
    )

    with pytest.raises(CredentialResolutionError):
        credential_secret_for_reference(
            credential_ref.id,
            purpose="provider",
            environ={},
        )

    assert (
        credential_secret_for_reference(
            credential_ref.id,
            purpose="provider",
            environ={"DGENTIC_REF_EXTERNAL_API_KEY": "sanitized-secret"},
        )
        == "sanitized-secret"
    )
    get_settings.cache_clear()


def test_external_generation_uses_process_credential_reference_at_transport_time(
    tmp_path,
    monkeypatch,
) -> None:
    adapter_script, marker_path = write_process_credential_adapter(
        tmp_path,
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n"
        "print('external-process-secret')\n",
    )
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_CREDENTIAL_PROCESS_ADAPTERS",
        json.dumps(
            {
                "process-vault": {
                    "argv": [sys.executable, adapter_script, str(marker_path)],
                }
            }
        ),
    )
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            source_type="external_process",
            adapter_id="process-vault",
            secret_name="providers/openai",
            label="external process provider",
        )
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "timeout_seconds": timeout_seconds,
            }
        )
        return FakeResponse(lm_studio_response("Hello from process credential."))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
        requested_by="operator",
    )
    external_provider = next(
        item for item in default_providers() if item.id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    )
    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )

    assert external_provider.enabled is True
    assert not marker_path.exists()

    provider_runtime.approve_provider_approval(approval.id, decided_by="reviewer")
    result = generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))
    approval_storage = (tmp_path / "state" / "provider-approvals.json").read_text(encoding="utf-8")
    credential_storage = (tmp_path / "state" / "credential-references.json").read_text(
        encoding="utf-8"
    )
    serialized_event = json.dumps(event_log.records, sort_keys=True, default=str)

    assert result.content == "Hello from process credential."
    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-process-secret",
            "timeout_seconds": 60.0,
        }
    ]
    assert marker_path.read_text(encoding="utf-8") == "providers/openai"
    assert "external-process-secret" not in approval_storage
    assert "external-process-secret" not in credential_storage
    assert "external-process-secret" not in serialized_event
    get_settings.cache_clear()


def test_external_process_credential_reference_skips_adapter_before_approval(
    tmp_path,
    monkeypatch,
) -> None:
    adapter_script, marker_path = write_process_credential_adapter(
        tmp_path,
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n"
        "print('external-process-secret')\n",
    )
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_CREDENTIAL_PROCESS_ADAPTERS",
        json.dumps({"process-vault": {"argv": [sys.executable, adapter_script, str(marker_path)]}}),
    )
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            source_type="external_process",
            adapter_id="process-vault",
            secret_name="providers/openai",
        )
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert not marker_path.exists()
    get_settings.cache_clear()


def test_external_process_credential_adapter_failure_preserves_approval(
    tmp_path,
    monkeypatch,
) -> None:
    adapter_script, marker_path = write_process_credential_adapter(
        tmp_path,
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n"
        "raise SystemExit(3)\n",
    )
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_CREDENTIAL_PROCESS_ADAPTERS",
        json.dumps({"process-vault": {"argv": [sys.executable, adapter_script, str(marker_path)]}}),
    )
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            source_type="external_process",
            adapter_id="process-vault",
            secret_name="providers/openai",
        )
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        raise AssertionError("transport should not be called when credential adapter fails")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
        requested_by="operator",
    )
    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(approval.id, decided_by="reviewer")

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))

    review = provider_runtime.get_provider_approval_review(approval.id)
    assert marker_path.read_text(encoding="utf-8") == "providers/openai"
    assert review.status == provider_runtime.ProviderApprovalStatus.approved
    assert review.executed_at is None
    get_settings.cache_clear()


@pytest.mark.parametrize("stream_name", ["stdout", "stderr"])
def test_external_process_credential_oversized_output_preserves_approval(
    tmp_path,
    monkeypatch,
    stream_name: str,
) -> None:
    write_target = "sys.stdout" if stream_name == "stdout" else "sys.stderr"
    adapter_script, marker_path = write_process_credential_adapter(
        tmp_path,
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n"
        f"{write_target}.write('x' * 4096)\n"
        f"{write_target}.flush()\n",
    )
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_CREDENTIAL_PROCESS_MAX_OUTPUT_BYTES", "32")
    monkeypatch.setenv(
        "DGENTIC_CREDENTIAL_PROCESS_ADAPTERS",
        json.dumps({"process-vault": {"argv": [sys.executable, adapter_script, str(marker_path)]}}),
    )
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            source_type="external_process",
            adapter_id="process-vault",
            secret_name="providers/openai",
        )
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        raise AssertionError("transport should not be called when credential output is oversized")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
        requested_by="operator",
    )
    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(approval.id, decided_by="reviewer")

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))

    review = provider_runtime.get_provider_approval_review(approval.id)
    assert marker_path.read_text(encoding="utf-8") == "providers/openai"
    assert review.status == provider_runtime.ProviderApprovalStatus.approved
    assert review.executed_at is None
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("purpose", "revoke_first"),
    [
        ("provider", True),
        ("runtime", False),
    ],
)
def test_external_process_reference_validation_skips_adapter(
    tmp_path,
    monkeypatch,
    purpose: str,
    revoke_first: bool,
) -> None:
    adapter_script, marker_path = write_process_credential_adapter(
        tmp_path,
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n"
        "print('external-process-secret')\n",
    )
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_CREDENTIAL_PROCESS_ADAPTERS",
        json.dumps({"process-vault": {"argv": [sys.executable, adapter_script, str(marker_path)]}}),
    )
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            source_type="external_process",
            adapter_id="process-vault",
            secret_name="providers/openai",
            purpose=purpose,
        )
    )
    if revoke_first:
        revoke_credential_reference(credential_ref.id)
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        provider_runtime.create_provider_approval(
            EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
            ),
        )

    assert not marker_path.exists()
    get_settings.cache_clear()


def test_external_approval_rejects_revoked_credential_reference_without_secret_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(env_var="DGENTIC_REF_EXTERNAL_API_KEY")
    )
    revoke_credential_reference(credential_ref.id)
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()
    blocked_credentials = BlockingCredentialEnviron()
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        provider_runtime.create_provider_approval(
            EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
            ),
        )

    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_approval_rejects_runtime_purpose_credential_reference(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    get_settings.cache_clear()
    credential_ref = create_credential_reference(
        CredentialReferenceRequest(
            env_var="DGENTIC_REF_RUNTIME_KEY",
            purpose="runtime",
        )
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    get_settings.cache_clear()
    blocked_credentials = BlockingCredentialEnviron()
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        provider_runtime.create_provider_approval(
            EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
            ),
        )

    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_generation_open_circuit_preserves_bound_approval_id(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    configure_external_provider(monkeypatch)
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise http_error(503)

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    first_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(first_approval.id, decided_by="reviewer")
    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request.model_copy(update={"approval_id": first_approval.id}))

    second_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(second_approval.id, decided_by="reviewer")
    with pytest.raises(provider_runtime.ProviderCircuitOpenError):
        generate_provider_completion(request.model_copy(update={"approval_id": second_approval.id}))

    approvals = {approval.id: approval for approval in provider_runtime.list_provider_approvals()}
    assert approvals[first_approval.id].status == provider_runtime.ProviderApprovalStatus.executed
    assert approvals[first_approval.id].executed_at is not None
    assert approvals[second_approval.id].status == provider_runtime.ProviderApprovalStatus.approved
    assert approvals[second_approval.id].executed_at is None
    assert calls == ["https://provider.example.test/v1/chat/completions"]
    get_settings.cache_clear()


def test_external_generation_open_circuit_skips_credential_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    configure_external_provider(monkeypatch)
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise http_error(503)

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    first_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(first_approval.id, decided_by="reviewer")
    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request.model_copy(update={"approval_id": first_approval.id}))

    blocked_credentials = BlockingCredentialEnviron()
    second_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(second_approval.id, decided_by="reviewer")
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)

    with pytest.raises(provider_runtime.ProviderCircuitOpenError):
        generate_provider_completion(request.model_copy(update={"approval_id": second_approval.id}))

    approvals = {approval.id: approval for approval in provider_runtime.list_provider_approvals()}
    assert approvals[second_approval.id].status == provider_runtime.ProviderApprovalStatus.approved
    assert approvals[second_approval.id].executed_at is None
    assert calls == ["https://provider.example.test/v1/chat/completions"]
    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_generation_circuit_is_per_configured_base_url_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    configure_external_provider(monkeypatch, base_url="https://provider.example.test")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if request.full_url == "https://provider.example.test/chat/completions":
            raise http_error(503)
        return FakeResponse(lm_studio_response("Pathful endpoint remains available."))

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    first_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(first_approval.id, decided_by="reviewer")
    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request.model_copy(update={"approval_id": first_approval.id}))

    configure_external_provider(monkeypatch, base_url="https://provider.example.test/v1")
    get_settings.cache_clear()
    second_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(second_approval.id, decided_by="reviewer")
    result = generate_provider_completion(
        request.model_copy(update={"approval_id": second_approval.id})
    )

    assert result.content == "Pathful endpoint remains available."
    assert calls == [
        "https://provider.example.test/chat/completions",
        "https://provider.example.test/v1/chat/completions",
    ]
    get_settings.cache_clear()


def test_bound_provider_approval_rejects_request_drift_denied_and_expired(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Bind this request."}],
        options={"top_p": 0.9},
        requested_by="operator",
    )
    drift_approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(drift_approval.id, decided_by="reviewer")

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError, match="not bound"):
        generate_provider_completion(
            request.model_copy(
                update={
                    "model": "gpt-other",
                    "approval_id": drift_approval.id,
                }
            )
        )
    with pytest.raises(ValueError, match="pending"):
        provider_runtime.deny_provider_approval(drift_approval.id, decided_by="reviewer")

    denied = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.deny_provider_approval(denied.id, decided_by="reviewer")
    with pytest.raises(ValueError, match="pending"):
        provider_runtime.approve_provider_approval(denied.id, decided_by="reviewer")
    with pytest.raises(provider_runtime.ProviderApprovalRequiredError, match="not executable"):
        generate_provider_completion(request.model_copy(update={"approval_id": denied.id}))

    expired = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(expired.id, decided_by="reviewer")
    approval_path = tmp_path / "state" / "provider-approvals.json"
    approvals = json.loads(approval_path.read_text(encoding="utf-8"))
    for approval in approvals:
        if approval["id"] == expired.id:
            approval["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    approval_path.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(provider_runtime.ProviderApprovalRequiredError, match="expired"):
        generate_provider_completion(request.model_copy(update={"approval_id": expired.id}))

    assert calls == []
    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_generation_rejects_plain_http_base_url_before_transport(monkeypatch) -> None:
    configure_external_provider(monkeypatch, base_url="http://provider.example.test/v1")
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderEgressPolicyError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )

    assert calls == []
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("mode", "expected_message"),
    [
        ("deny", "denied by network policy"),
        ("approval_required", "requires network approval"),
    ],
)
def test_provider_generation_rejects_network_domain_policy_before_transport(
    mode,
    expected_message,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_LM_STUDIO_BASE_URL", "http://provider.example.test:1234")
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "provider.example.test",
                        "mode": mode,
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_post_json(
        url: str,
        payload: dict,
        timeout_seconds: float,
        *,
        headers: dict | None = None,
    ) -> dict:
        calls.append(url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    with pytest.raises(provider_runtime.ProviderEgressPolicyError, match=expected_message):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert calls == []
    get_settings.cache_clear()


def test_provider_generation_audit_network_domain_policy_allows_transport(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_LM_STUDIO_BASE_URL", "http://provider.example.test:1234")
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "default_mode": "deny",
                "rules": [
                    {
                        "domain": "provider.example.test",
                        "mode": "audit",
                    }
                ],
            }
        ),
    )
    get_settings.cache_clear()
    calls: list[dict] = []

    def fake_post_json(
        url: str,
        payload: dict,
        timeout_seconds: float,
        *,
        headers: dict | None = None,
    ) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return json.loads(lm_studio_response("Allowed by audit mode.").decode("utf-8"))

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert calls == [
        {
            "url": "http://provider.example.test:1234/v1/chat/completions",
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "Say hello."}],
                "stream": False,
            },
            "timeout_seconds": 60.0,
        }
    ]
    assert result.content == "Allowed by audit mode."
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("base_url", "api_key_env", "api_key", "models"),
    [
        ("https://provider.example.test/v1", "DGENTIC_TEST_EXTERNAL_API_KEY", "", "gpt-test"),
        ("", "DGENTIC_TEST_EXTERNAL_API_KEY", "external-api-key-secret", "gpt-test"),
        ("", "", "", ""),
        (
            "https://provider.example.test/v1",
            "DGENTIC_TEST_EXTERNAL_API_KEY",
            "external-api-key-secret",
            "",
        ),
    ],
)
def test_external_generation_requires_configuration_before_transport(
    base_url,
    api_key_env,
    api_key,
    models,
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()
    calls: list[str] = []
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", base_url)
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", api_key_env)
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", models)
    if api_key_env:
        if api_key:
            monkeypatch.setenv(api_key_env, api_key)
        else:
            monkeypatch.delenv(api_key_env, raising=False)
    get_settings.cache_clear()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )

    assert calls == []
    serialized_event = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "external-api-key-secret" not in serialized_event
    get_settings.cache_clear()


def test_external_generation_missing_credential_does_not_claim_bound_approval(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider(monkeypatch, api_key="")
    tracked_credentials = TrackingCredentialEnviron(
        key="DGENTIC_TEST_EXTERNAL_API_KEY",
        value="",
    )
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", tracked_credentials)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Say hello."}],
    )
    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(approval.id, decided_by="reviewer")

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        generate_provider_completion(request.model_copy(update={"approval_id": approval.id}))

    stored_approval = provider_runtime.list_provider_approvals()[0]
    assert stored_approval.status == provider_runtime.ProviderApprovalStatus.approved
    assert stored_approval.executed_at is None
    assert calls == []
    assert tracked_credentials.calls == ["DGENTIC_TEST_EXTERNAL_API_KEY"]
    get_settings.cache_clear()


def test_provider_approval_requires_credential_env_name_without_secret_lookup(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    blocked_credentials = BlockingCredentialEnviron()
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)
    get_settings.cache_clear()

    with pytest.raises(provider_runtime.ProviderConfigurationError):
        provider_runtime.create_provider_approval(
            EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
            ),
        )

    assert blocked_credentials.calls == []
    get_settings.cache_clear()


def test_external_generation_rejects_runtime_base_url_before_transport(monkeypatch) -> None:
    configure_external_provider(monkeypatch)
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderEgressPolicyError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                base_url="https://evil.example.test/v1",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert calls == []
    get_settings.cache_clear()


def test_local_provider_cannot_use_external_configured_base_url(monkeypatch) -> None:
    configure_external_provider(monkeypatch)
    event_log = RecordingEventLog()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderEgressPolicyError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="gpt-not-checked-through-external-adapter",
                base_url="https://provider.example.test/v1",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )

    assert calls == []
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderEgressPolicyError"
    get_settings.cache_clear()


def test_provider_policy_does_not_globally_allow_external_configured_base_url(
    monkeypatch,
) -> None:
    configure_external_provider(monkeypatch)
    settings = get_settings()

    with pytest.raises(ProviderEgressPolicyError):
        validate_provider_base_url(
            provider_id="lm-studio",
            base_url="https://provider.example.test/v1",
            settings=settings,
        )

    assert "https://provider.example.test/v1" not in allowed_provider_base_urls(settings)
    assert (
        validate_provider_base_url(
            provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            base_url="https://provider.example.test/v1",
            settings=settings,
        )
        == "https://provider.example.test/v1"
    )
    get_settings.cache_clear()


def test_local_provider_can_use_extra_trusted_base_url(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_ALLOWED_BASE_URLS", "http://127.0.0.1:4321")
    get_settings.cache_clear()
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-extra",
        "model": "local-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Extra local endpoint."},
                "finish_reason": "stop",
            }
        ],
    }

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return raw_response

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            base_url="http://127.0.0.1:4321",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert result.content == "Extra local endpoint."
    assert calls == [
        {
            "url": "http://127.0.0.1:4321/v1/chat/completions",
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "Say hello."}],
                "stream": False,
            },
            "timeout_seconds": 60.0,
        }
    ]
    get_settings.cache_clear()


def test_external_generation_rejects_model_outside_allowlist_before_transport(
    monkeypatch,
) -> None:
    configure_external_provider(monkeypatch, models="gpt-test")
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(ValueError):
        generate_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-not-allowed",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )

    assert calls == []
    get_settings.cache_clear()


def test_external_generation_redacts_upstream_secret_metadata(monkeypatch) -> None:
    configure_external_provider(monkeypatch)
    event_log = RecordingEventLog()
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-external",
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "External content."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        "authorization": "Bearer upstream-response-secret",
        "token": "upstream-token-secret",
    }

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append({"authorization": request.get_header("Authorization")})
        return FakeResponse(json.dumps(raw_response).encode("utf-8"))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            model="gpt-test",
            messages=[{"role": "user", "content": "Say hello."}],
            approved=True,
        )
    )

    assert calls == [{"authorization": "Bearer external-api-key-secret"}]
    serialized_result = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    serialized_events = json.dumps(event_log.records, sort_keys=True, default=str)
    for raw_secret in [
        "external-api-key-secret",
        "upstream-response-secret",
        "upstream-token-secret",
    ]:
        assert raw_secret not in serialized_result
        assert raw_secret not in serialized_events
    assert "External content." in serialized_result
    assert "External content." not in serialized_events
    get_settings.cache_clear()


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


def test_provider_generation_opens_circuit_after_retry_exhaustion_and_fails_fast(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()
    event_log = RecordingEventLog()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise http_error(503)

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )

    request = ProviderGenerationRequest(
        provider_id="lm-studio",
        model="local-model",
        base_url="http://127.0.0.1:1234",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    for _ in range(2):
        with pytest.raises(provider_transport.ProviderRetryExhaustedError):
            generate_provider_completion(request)

    with pytest.raises(provider_runtime.ProviderCircuitOpenError):
        generate_provider_completion(request)

    assert len(calls) == 2
    assert event_log.records[-1]["metadata"]["error_type"] == "ProviderCircuitOpenError"
    get_settings.cache_clear()


def test_provider_generation_circuit_cooldown_allows_probe_and_reset(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(503)
        return FakeResponse(lm_studio_response("Recovered after cooldown."))

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )

    request = ProviderGenerationRequest(
        provider_id="lm-studio",
        model="local-model",
        base_url="http://127.0.0.1:1234",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request)
    result = generate_provider_completion(request)

    assert result.content == "Recovered after cooldown."
    assert len(calls) == 2
    get_settings.cache_clear()


def test_provider_generation_circuit_is_per_provider(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if request.full_url.endswith("/v1/chat/completions"):
            raise http_error(503)
        return FakeResponse(
            json.dumps(
                {
                    "message": {"role": "assistant", "content": "Ollama remains available."},
                    "done": True,
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
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
    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="ollama",
            model="llama3.1",
            base_url="http://127.0.0.1:11434",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert result.content == "Ollama remains available."
    assert any(call.endswith("/api/chat") for call in calls)
    get_settings.cache_clear()


def test_provider_generation_circuit_is_per_base_url(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_ALLOWED_BASE_URLS", "http://127.0.0.1:4321")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if request.full_url.startswith("http://127.0.0.1:1234"):
            raise http_error(503)
        return FakeResponse(lm_studio_response("Alternate endpoint remains available."))

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
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
    result = generate_provider_completion(
        ProviderGenerationRequest(
            provider_id="lm-studio",
            model="local-model",
            base_url="http://127.0.0.1:4321",
            messages=[{"role": "user", "content": "Say hello."}],
        )
    )

    assert result.content == "Alternate endpoint remains available."
    assert any(call.startswith("http://127.0.0.1:4321") for call in calls)
    get_settings.cache_clear()


def test_provider_generation_open_circuit_allows_single_half_open_probe(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()
    calls: list[str] = []
    probe_started = False

    def fake_open_provider_request(request, *, timeout_seconds: float):
        nonlocal probe_started
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(503)
        probe_started = True
        with pytest.raises(provider_runtime.ProviderCircuitOpenError):
            generate_provider_completion(
                ProviderGenerationRequest(
                    provider_id="lm-studio",
                    model="local-model",
                    base_url="http://127.0.0.1:1234",
                    messages=[{"role": "user", "content": "Concurrent call."}],
                )
            )
        return FakeResponse(lm_studio_response("Half-open probe succeeded."))

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id="lm-studio",
        model="local-model",
        base_url="http://127.0.0.1:1234",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request)
    result = generate_provider_completion(request)

    assert probe_started is True
    assert result.content == "Half-open probe succeeded."
    assert len(calls) == 2
    get_settings.cache_clear()


def test_provider_generation_half_open_rejections_preserve_probe_lock(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(503)
        if len(calls) == 2:
            for _ in range(2):
                with pytest.raises(provider_runtime.ProviderCircuitOpenError):
                    generate_provider_completion(
                        ProviderGenerationRequest(
                            provider_id="lm-studio",
                            model="local-model",
                            base_url="http://127.0.0.1:1234",
                            messages=[{"role": "user", "content": "Concurrent call."}],
                        )
                    )
            return FakeResponse(lm_studio_response("Half-open probe kept the lock."))
        raise AssertionError("concurrent half-open call reached provider transport")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id="lm-studio",
        model="local-model",
        base_url="http://127.0.0.1:1234",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request)
    result = generate_provider_completion(request)

    assert result.content == "Half-open probe kept the lock."
    assert len(calls) == 2
    get_settings.cache_clear()


def test_provider_generation_half_open_probe_failure_reopens_circuit(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(503)
        return FakeResponse(b'{"choices": []}')

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id="lm-studio",
        model="local-model",
        base_url="http://127.0.0.1:1234",
        messages=[{"role": "user", "content": "Say hello."}],
    )

    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        generate_provider_completion(request)
    for state in provider_runtime._provider_circuit_state.values():
        state["opened_at"] = provider_runtime.perf_counter() - 61
    with pytest.raises(provider_runtime.ProviderUpstreamResponseError):
        generate_provider_completion(request)
    with pytest.raises(provider_runtime.ProviderCircuitOpenError):
        generate_provider_completion(request)

    assert len(calls) == 2
    get_settings.cache_clear()


def test_provider_stream_half_open_close_reopens_and_allows_next_probe(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()
    calls: list[str] = []
    probe_responses: list[FakeStreamResponse] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(503)
        if len(calls) == 2:
            response = FakeStreamResponse(
                openai_stream_lines(
                    {
                        "id": "chatcmpl-half-open",
                        "model": "local-model",
                        "choices": [
                            {"index": 0, "delta": {"content": "Partial"}, "finish_reason": None}
                        ],
                    },
                    done=False,
                )
            )
            probe_responses.append(response)
            return response
        if len(calls) == 3:
            return FakeStreamResponse(
                openai_stream_lines(
                    {
                        "id": "chatcmpl-half-open-retry",
                        "model": "local-model",
                        "choices": [
                            {"index": 0, "delta": {"content": "Recovered"}, "finish_reason": None}
                        ],
                    },
                    {
                        "id": "chatcmpl-half-open-retry",
                        "model": "local-model",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    },
                )
            )
        raise AssertionError("unexpected stream probe transport call")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    request = ProviderGenerationRequest(
        provider_id="lm-studio",
        model="local-model",
        base_url="http://127.0.0.1:1234",
        messages=[{"role": "user", "content": "Stream hello."}],
    )

    with pytest.raises(provider_transport.ProviderRetryExhaustedError):
        list(provider_runtime.stream_provider_completion(request))
    stream = provider_runtime.stream_provider_completion(request)
    first_event = next(stream)
    stream.close()
    events = list(provider_runtime.stream_provider_completion(request))

    assert first_event.delta == "Partial"
    assert probe_responses[0].closed is True
    assert [event.delta for event in events] == ["Recovered", ""]
    assert len(calls) == 3
    get_settings.cache_clear()


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


def test_lm_studio_streaming_emits_ordered_chunks_and_safe_logs(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []
    stream_response = FakeStreamResponse(
        openai_stream_lines(
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "model": "local-model",
                "choices": [{"index": 0, "delta": {"content": "Hel"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "model": "local-model",
                "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": None}],
            },
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "model": "local-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
            {
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "model": "local-model",
                "choices": [],
                "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
            },
        )
    )

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.headers),
                "payload": json.loads(request.data.decode("utf-8")),
                "timeout_seconds": timeout_seconds,
            }
        )
        return stream_response

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                base_url="http://127.0.0.1:1234",
                messages=[{"role": "user", "content": "Say hello."}],
                temperature=0.2,
                max_tokens=32,
            )
        )
    )

    assert calls == [
        {
            "url": "http://127.0.0.1:1234/v1/chat/completions",
            "headers": {"Accept": "text/event-stream", "Content-type": "application/json"},
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "Say hello."}],
                "stream": True,
                "temperature": 0.2,
                "max_tokens": 32,
            },
            "timeout_seconds": 60.0,
        }
    ]
    assert [event.delta for event in events] == ["Hel", "lo", "", ""]
    assert events[-2].finish_reason == "stop"
    assert events[-2].estimated_cost_usd is None
    assert events[-1].usage_metadata == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert events[-1].estimated_cost_usd == 0.0
    assert stream_response.closed is True
    completion_metadata = event_log.records[-1]["metadata"]
    assert completion_metadata["chunk_count"] == 4
    assert completion_metadata["content_length"] == len("Hello")
    assert completion_metadata["usage_metadata"] == events[-1].usage_metadata
    assert completion_metadata["estimated_cost_usd"] == 0.0
    assert completion_metadata["finish_reasons"] == ["stop"]
    serialized_event = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "Hello" not in serialized_event


def test_ollama_streaming_posts_chat_payload_and_emits_ordered_chunks(
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()
    calls: list[dict] = []
    stream_response = FakeStreamResponse(
        [
            json.dumps(
                {
                    "model": "llama3.1",
                    "message": {"role": "assistant", "content": "delta-secret-"},
                    "done": False,
                }
            )
            + "\n",
            json.dumps(
                {
                    "model": "llama3.1",
                    "message": {"role": "assistant", "content": "abc"},
                    "done": False,
                }
            )
            + "\n",
            json.dumps(
                {
                    "model": "llama3.1",
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 12345,
                    "prompt_eval_count": 4,
                    "eval_count": 2,
                }
            )
            + "\n",
        ]
    )

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "headers": dict(request.headers),
                "payload": json.loads(request.data.decode("utf-8")),
                "timeout_seconds": timeout_seconds,
            }
        )
        return stream_response

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id="ollama",
                model="llama3.1",
                base_url="http://127.0.0.1:11434/",
                messages=[{"role": "user", "content": "prompt-secret-123"}],
                options={"num_ctx": 4096},
                temperature=0.2,
                max_tokens=128,
            )
        )
    )

    assert calls == [
        {
            "url": "http://127.0.0.1:11434/api/chat",
            "headers": {"Accept": "application/x-ndjson", "Content-type": "application/json"},
            "payload": {
                "model": "llama3.1",
                "messages": [{"role": "user", "content": "prompt-secret-123"}],
                "options": {"num_ctx": 4096, "temperature": 0.2, "num_predict": 128},
                "stream": True,
            },
            "timeout_seconds": 60.0,
        }
    ]
    assert [event.delta for event in events] == ["delta-secret-", "abc", ""]
    assert events[-1].finish_reason == "stop"
    assert events[-1].usage_metadata == {
        "prompt_tokens": 4,
        "completion_tokens": 2,
        "total_tokens": 6,
    }
    assert events[-1].estimated_cost_usd == 0.0
    assert events[-1].raw_response_metadata == {
        "done": True,
        "done_reason": "stop",
        "total_duration": 12345,
        "prompt_eval_count": 4,
        "eval_count": 2,
        "message_role": "assistant",
    }
    assert stream_response.closed is True
    completion_metadata = event_log.records[-1]["metadata"]
    assert completion_metadata["chunk_count"] == 3
    assert completion_metadata["content_length"] == len("delta-secret-abc")
    assert completion_metadata["finish_reasons"] == ["stop"]
    assert completion_metadata["usage_metadata"] == events[-1].usage_metadata
    assert completion_metadata["estimated_cost_usd"] == 0.0
    serialized_event = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "prompt-secret-123" not in serialized_event
    assert "delta-secret-abc" not in serialized_event
    assert "delta-secret-" not in serialized_event


def test_ollama_streaming_malformed_first_chunk_raises_safe_error(
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(['{"not": "valid"\n'])

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_transport.ProviderUpstreamResponseError):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id="ollama",
                    model="llama3.1",
                    base_url="http://127.0.0.1:11434",
                    messages=[{"role": "user", "content": "Say hello."}],
                )
            )
        )

    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert '{"not": "valid"' not in serialized


def test_ollama_streaming_error_first_chunk_raises_safe_error(
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse([json.dumps({"error": "ollama-upstream-error-secret"}) + "\n"])

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_transport.ProviderUpstreamResponseError):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id="ollama",
                    model="llama3.1",
                    base_url="http://127.0.0.1:11434",
                    messages=[{"role": "user", "content": "prompt-secret-123"}],
                )
            )
        )

    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "ollama-upstream-error-secret" not in serialized
    assert "prompt-secret-123" not in serialized


def test_ollama_streaming_failure_after_first_chunk_emits_sanitized_error_event(
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            [
                json.dumps(
                    {
                        "model": "llama3.1",
                        "message": {"role": "assistant", "content": "Visible"},
                        "done": False,
                    }
                )
                + "\n",
                '{"not": "valid"\n',
            ]
        )

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id="ollama",
                model="llama3.1",
                base_url="http://127.0.0.1:11434",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )
    )

    assert [event.delta for event in events] == ["Visible", ""]
    assert events[-1].event == "error"
    assert events[-1].error == "Provider request failed."
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "Visible" not in serialized
    assert '{"not": "valid"' not in serialized


def test_ollama_streaming_error_after_first_chunk_emits_sanitized_error_event(
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            [
                json.dumps(
                    {
                        "model": "llama3.1",
                        "message": {"role": "assistant", "content": "delta-secret-abc"},
                        "done": False,
                    }
                )
                + "\n",
                json.dumps({"error": "ollama-upstream-error-secret"}) + "\n",
            ]
        )

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id="ollama",
                model="llama3.1",
                base_url="http://127.0.0.1:11434",
                messages=[{"role": "user", "content": "prompt-secret-123"}],
            )
        )
    )

    assert [event.delta for event in events] == ["delta-secret-abc", ""]
    assert events[-1].event == "error"
    assert events[-1].error == "Provider request failed."
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "delta-secret-abc" not in serialized
    assert "ollama-upstream-error-secret" not in serialized
    assert "prompt-secret-123" not in serialized


def test_external_streaming_sends_authorization_and_redacts_logs(monkeypatch) -> None:
    configure_external_provider(monkeypatch)
    event_log = RecordingEventLog()
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-external-stream",
                    "model": "gpt-test",
                    "choices": [
                        {"index": 0, "delta": {"content": "Secretless"}, "finish_reason": None}
                    ],
                    "authorization": "Bearer upstream-stream-secret",
                },
                {
                    "id": "chatcmpl-external-stream",
                    "model": "gpt-test",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            )
        )

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )
    )

    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "Say hello."}],
                "stream": True,
            },
        }
    ]
    assert [event.delta for event in events] == ["Secretless", ""]
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "external-api-key-secret" not in serialized
    assert "upstream-stream-secret" not in serialized
    assert "Secretless" not in serialized
    get_settings.cache_clear()


def test_external_streaming_uses_request_model_pricing_for_usage_chunk(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": 0.5,
                        "completion_usd_per_1k_tokens": 1.0,
                        "request_estimate_usd": 0.02,
                    }
                }
            }
        ),
    )
    configure_external_provider(monkeypatch)
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-external-stream",
                    "model": "provider-controlled-model-secret",
                    "choices": [
                        {"index": 0, "delta": {"content": "Priced"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "chatcmpl-external-stream",
                    "model": "provider-controlled-model-secret",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
                {
                    "id": "chatcmpl-external-stream",
                    "model": "provider-controlled-model-secret",
                    "choices": [],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
                },
            )
        )

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                model="gpt-test",
                messages=[{"role": "user", "content": "Say hello."}],
                approved=True,
            )
        )
    )

    assert events[-1].model == "gpt-test"
    assert events[-1].usage_metadata == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert events[-1].estimated_cost_usd == 0.009
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "provider-controlled-model-secret" not in serialized
    assert "Priced" not in serialized
    get_settings.cache_clear()


def test_external_streaming_accepts_bound_approval_id_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider(monkeypatch)
    calls: list[dict] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-approved-stream",
                    "model": "gpt-test",
                    "choices": [
                        {"index": 0, "delta": {"content": "Approved"}, "finish_reason": None}
                    ],
                    "authorization": "Bearer upstream-stream-secret",
                },
                {
                    "id": "chatcmpl-approved-stream",
                    "model": "gpt-test",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    request = ProviderGenerationRequest(
        provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        model="gpt-test",
        messages=[{"role": "user", "content": "Stream this response."}],
        stream=True,
        requested_by="operator",
    )
    approval = provider_runtime.create_provider_approval(
        EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
        request,
    )
    provider_runtime.approve_provider_approval(approval.id, decided_by="reviewer")

    events = list(
        provider_runtime.stream_provider_completion(
            request.model_copy(update={"approval_id": approval.id})
        )
    )

    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "Stream this response."}],
                "stream": True,
            },
        }
    ]
    assert [event.delta for event in events] == ["Approved", ""]
    assert provider_runtime.list_provider_approvals()[0].status == (
        provider_runtime.ProviderApprovalStatus.executed
    )
    get_settings.cache_clear()


def test_streaming_open_retries_429_then_succeeds(monkeypatch) -> None:
    event_log = RecordingEventLog()
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(429, headers={"Retry-After": "2"})
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-stream-retry",
                    "model": "local-model",
                    "choices": [
                        {"index": 0, "delta": {"content": "Recovered"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "chatcmpl-stream-retry",
                    "model": "local-model",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            )
        )

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                base_url="http://127.0.0.1:1234",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )
    )

    assert [event.delta for event in events] == ["Recovered", ""]
    assert len(calls) == 2
    assert sleeps == [2.0]
    completion_metadata = event_log.records[-1]["metadata"]
    assert completion_metadata["attempt_count"] == 2
    assert completion_metadata["retry_count"] == 1
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "Recovered" not in serialized
    assert "provider-error-secret" not in serialized


def test_streaming_malformed_first_chunk_raises_safe_error(monkeypatch) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(['data: {"not": "valid"\n'])

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_transport.ProviderUpstreamResponseError):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id="lm-studio",
                    model="local-model",
                    base_url="http://127.0.0.1:1234",
                    messages=[{"role": "user", "content": "Say hello."}],
                )
            )
        )

    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert '{"not": "valid"' not in serialized
    assert "Say hello." not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"message": "stream-upstream-error-secret"}},
        {"choices": []},
        {"choices": [{"index": 0, "delta": "not-an-object", "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": {"secret": "stream-content"}}}]},
    ],
)
def test_openai_compatible_streaming_rejects_malformed_success_chunks(
    payload,
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(openai_stream_lines(payload))

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_transport.ProviderUpstreamResponseError):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id="lm-studio",
                    model="local-model",
                    base_url="http://127.0.0.1:1234",
                    messages=[{"role": "user", "content": "prompt-secret-123"}],
                )
            )
        )

    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    assert failure_metadata["error"] == "Provider request failed."
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "prompt-secret-123" not in serialized
    assert "stream-upstream-error-secret" not in serialized
    assert "stream-content" not in serialized


def test_streaming_failure_after_first_chunk_emits_sanitized_error_event(
    monkeypatch,
) -> None:
    event_log = RecordingEventLog()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-stream",
                    "model": "local-model",
                    "choices": [
                        {"index": 0, "delta": {"content": "Visible"}, "finish_reason": None}
                    ],
                },
                done=False,
            )
            + ['data: {"not": "valid"\n']
        )

    monkeypatch.setattr(provider_runtime, "event_log", event_log)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    events = list(
        provider_runtime.stream_provider_completion(
            ProviderGenerationRequest(
                provider_id="lm-studio",
                model="local-model",
                base_url="http://127.0.0.1:1234",
                messages=[{"role": "user", "content": "Say hello."}],
            )
        )
    )

    assert events[0].delta == "Visible"
    assert events[-1].event == "error"
    assert events[-1].error == "Provider request failed."
    failure_metadata = event_log.records[-1]["metadata"]
    assert failure_metadata["error_type"] == "ProviderUpstreamResponseError"
    serialized = json.dumps(event_log.records, sort_keys=True, default=str)
    assert "Visible" not in serialized
    assert '{"not": "valid"' not in serialized


@pytest.mark.parametrize("provider_id", ["external-placeholder"])
def test_streaming_rejects_unsupported_provider_before_transport(
    provider_id,
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)

    with pytest.raises(provider_runtime.ProviderFeatureNotSupportedError):
        list(
            provider_runtime.stream_provider_completion(
                ProviderGenerationRequest(
                    provider_id=provider_id,
                    model="local-model",
                    messages=[{"role": "user", "content": "Say hello."}],
                )
            )
        )

    assert calls == []


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
