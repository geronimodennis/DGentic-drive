import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dgentic import provider_runtime
from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.settings import get_settings

PROVIDER_ID = provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID


@pytest.fixture()
def dashboard_approval_client(tmp_path, monkeypatch) -> tuple[TestClient, Path]:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "provider.example.test",
                        "mode": "approval_required",
                        "reason": "Review provider token=network-policy-secret.",
                    }
                ]
            }
        ),
    )
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "TEST_PROVIDER_KEY")
    monkeypatch.setenv("TEST_PROVIDER_KEY", "provider-api-key-secret")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    reset_database_state()
    get_settings.cache_clear()
    yield TestClient(create_app()), root_dir
    reset_database_state()
    get_settings.cache_clear()


def _generate_approval_tool(client: TestClient, name: str) -> None:
    response = client.post(
        "/tools/generate",
        json={
            "name": name,
            "description": "Dashboard approval contract tool.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": (
                "def run(payload):\n    return {'ok': True, 'value': payload.get('value')}\n"
            ),
        },
    )

    assert response.status_code == 201


def _provider_approval_payload() -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "TOKEN=provider-prompt-secret"}],
        "temperature": 0.2,
        "max_tokens": 32,
        "agent_role": "developer",
        "task_id": "sprint-16",
    }


def _create_dashboard_approvals(
    client: TestClient,
    root_dir: Path,
    *,
    tool_name: str,
    filesystem_requested_by: bool = True,
    network_url: str = "https://provider.example.test/v1?token=network-url-secret",
    network_requested_by: str = "dashboard SECRET=network-requester-secret",
    network_agent_context: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    (root_dir / "delete-me.txt").write_text("remove", encoding="utf-8")
    _generate_approval_tool(client, tool_name)
    filesystem_payload: dict[str, Any] = {
        "path": "delete-me.txt",
        "action": "delete",
    }
    if filesystem_requested_by:
        filesystem_payload["requested_by"] = "dashboard SECRET=filesystem-requester-secret"

    create_calls: dict[str, Callable[[], Any]] = {
        "cli": lambda: client.post(
            "/cli/approvals?requested_by=dashboard SECRET=cli-requester-secret",
            json={"command": "python --version", "timeout_seconds": 10},
        ),
        "filesystem": lambda: client.post(
            "/filesystem/approvals",
            json=filesystem_payload,
        ),
        "network": lambda: client.post(
            "/network/approvals",
            json={
                "url": network_url,
                "surface": "provider",
                "action": "generate",
                "requested_by": network_requested_by,
                **(network_agent_context or {}),
            },
        ),
        "provider": lambda: client.post(
            (
                f"/providers/{PROVIDER_ID}/approvals"
                "?requested_by=dashboard SECRET=provider-requester-secret"
            ),
            json=_provider_approval_payload(),
        ),
        "tool": lambda: client.post(
            f"/tools/{tool_name}/approvals?requested_by=dashboard SECRET=tool-requester-secret",
            json={
                "payload": {"value": "TOKEN=tool-payload-secret"},
                "timeout_seconds": 5,
                "agent_role": "developer",
                "task_id": "sprint-16",
            },
        ),
    }
    endpoints = {
        "cli": "/cli/approvals",
        "filesystem": "/filesystem/approvals",
        "network": "/network/approvals",
        "provider": "/providers/approvals",
        "tool": "/tools/approvals",
    }

    approvals: dict[str, dict[str, Any]] = {}
    for source, create_call in create_calls.items():
        create_response = create_call()
        assert create_response.status_code == 201
        approvals[source] = {
            "create": create_response.json(),
            "base": endpoints[source],
        }
    return approvals


def test_unified_approval_inbox_contract_covers_all_sources(
    dashboard_approval_client,
) -> None:
    client, root_dir = dashboard_approval_client
    approvals = _create_dashboard_approvals(
        client,
        root_dir,
        tool_name="dashboard-contract-tool",
    )
    expected_requires_bound = {
        "cli": False,
        "filesystem": True,
        "network": True,
        "provider": True,
        "tool": True,
    }

    for source, contract in approvals.items():
        approval_id = contract["create"]["id"]
        base = contract["base"]
        list_response = client.get(f"{base}?status=pending")
        review_response = client.get(f"{base}/{approval_id}/review")
        approve_response = client.post(
            f"{base}/{approval_id}/approve",
            json={
                "decided_by": "reviewer TOKEN=decision-actor-secret",
                "reason": "Approved PASSWORD=decision-reason-secret",
            },
        )
        approved_review_response = client.get(f"{base}/{approval_id}/review")

        assert contract["create"]["status"] == "pending"
        assert contract["create"]["requested_by"].startswith("dashboard SECRET=[REDACTED]")
        assert list_response.status_code == 200
        assert any(item["id"] == approval_id for item in list_response.json())
        assert review_response.status_code == 200
        assert review_response.json()["id"] == approval_id
        assert review_response.json()["status"] == "pending"
        assert review_response.json()["requested_by"].startswith("dashboard SECRET=[REDACTED]")
        assert (
            review_response.json()["requires_bound_execution_request"]
            is (expected_requires_bound[source])
        )
        assert review_response.json()["direct_execute_available"] is False
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"
        assert approve_response.json()["decided_by"] == "reviewer TOKEN=[REDACTED]"
        assert approved_review_response.status_code == 200
        assert approved_review_response.json()["status"] == "approved"
        assert (
            approved_review_response.json()["requires_bound_execution_request"]
            is (expected_requires_bound[source])
        )
        assert approved_review_response.json()["direct_execute_available"] is (source == "cli")

    serialized = json.dumps(approvals)
    for secret in [
        "cli-requester-secret",
        "filesystem-requester-secret",
        "network-requester-secret",
        "network-url-secret",
        "provider-requester-secret",
        "provider-prompt-secret",
        "tool-requester-secret",
        "tool-payload-secret",
        "decision-actor-secret",
        "decision-reason-secret",
    ]:
        assert secret not in serialized


def test_dashboard_bound_execution_contract_fields_match_backend_consumers(
    dashboard_approval_client,
    monkeypatch,
) -> None:
    client, root_dir = dashboard_approval_client
    approvals = _create_dashboard_approvals(
        client,
        root_dir,
        tool_name="dashboard-execution-tool",
        filesystem_requested_by=False,
        network_url="https://provider.example.test/v1",
        network_requested_by="dashboard SECRET=provider-requester-secret",
        network_agent_context={"agent_role": "developer", "task_id": "sprint-16"},
    )
    provider_calls: list[dict[str, Any]] = []

    def fake_post_json(
        url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        provider_calls.append(
            {
                "url": url,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "headers": headers or {},
            }
        )
        return {
            "id": "chatcmpl-dashboard-approval-contract",
            "model": "gpt-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Approved dashboard response."},
                    "finish_reason": "stop",
                }
            ],
        }

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)

    for contract in approvals.values():
        approval_id = contract["create"]["id"]
        base = contract["base"]
        approve_response = client.post(
            f"{base}/{approval_id}/approve",
            json={"decided_by": "reviewer", "reason": "Bound execution smoke."},
        )
        assert approve_response.status_code == 200

    cli_id = approvals["cli"]["create"]["id"]
    filesystem_id = approvals["filesystem"]["create"]["id"]
    network_id = approvals["network"]["create"]["id"]
    provider_id = approvals["provider"]["create"]["id"]
    tool_id = approvals["tool"]["create"]["id"]

    cli_execute_response = client.post(f"/cli/approvals/{cli_id}/execute")
    filesystem_execute_response = client.post(
        "/filesystem/delete",
        json={"path": "delete-me.txt", "approval_id": filesystem_id},
    )
    provider_execute_response = client.post(
        "/providers/generate",
        json={
            **_provider_approval_payload(),
            "approval_id": provider_id,
            "network_approval_id": network_id,
            "requested_by": "dashboard SECRET=provider-requester-secret",
        },
    )
    tool_execute_response = client.post(
        "/tools/dashboard-execution-tool/execute",
        json={
            "payload": {"value": "TOKEN=tool-payload-secret"},
            "approval_id": tool_id,
            "timeout_seconds": 5,
            "requested_by": "dashboard SECRET=tool-requester-secret",
            "agent_role": "developer",
            "task_id": "sprint-16",
        },
    )
    cli_runs_response = client.get("/cli/runs")
    network_executed_response = client.get("/network/approvals?status=executed")

    assert cli_execute_response.status_code == 200
    assert cli_runs_response.status_code == 200
    assert any(run["approval_id"] == cli_id for run in cli_runs_response.json())
    assert filesystem_execute_response.status_code == 200
    assert provider_execute_response.status_code == 200
    assert provider_execute_response.json()["content"] == "Approved dashboard response."
    assert tool_execute_response.status_code == 200
    assert tool_execute_response.json()["approval_id"] == tool_id
    assert network_executed_response.status_code == 200
    assert any(item["id"] == network_id for item in network_executed_response.json())
    assert provider_calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "TOKEN=provider-prompt-secret"}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 32,
            },
            "timeout_seconds": 60.0,
            "headers": {"Authorization": "Bearer provider-api-key-secret"},
        }
    ]
