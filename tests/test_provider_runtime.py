import pytest

from dgentic import provider_runtime
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
            base_url="http://localhost:11434/",
            messages=[{"role": "user", "content": "Say hello."}],
            options={"num_ctx": 4096},
            temperature=0.2,
            max_tokens=128,
            timeout_seconds=5,
        )
    )

    assert calls == [
        {
            "url": "http://localhost:11434/api/chat",
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
    assert result.raw_response_metadata == raw_response
    assert result.duration_ms >= 0
    assert [record["message"] for record in event_log.records] == [
        "Started provider generation.",
        "Completed provider generation.",
    ]
    assert all(record["event_type"] == LogEventType.provider for record in event_log.records)


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
            base_url="http://localhost:1234",
            messages=[{"role": "user", "content": "Say hello."}],
            temperature=0.1,
            max_tokens=64,
            timeout_seconds=7,
        )
    )

    assert calls == [
        {
            "url": "http://localhost:1234/v1/chat/completions",
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "Say hello."}],
                "temperature": 0.1,
                "max_tokens": 64,
            },
            "timeout_seconds": 7,
        }
    ]
    assert result.provider_id == "lm-studio"
    assert result.model == "local-model"
    assert result.content == "Hello from LM Studio."
    assert result.raw_response_metadata == raw_response
    assert result.duration_ms >= 0
    assert event_log.records[-1]["metadata"]["content"] == "Hello from LM Studio."


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
