import base64
import json
import time
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from dgentic.api.routes import cli_runtime_service
from dgentic.cli_runtime import CommandRun, CommandRunStatus, ProcessSnapshot
from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.redaction import REDACTED_SECRET_MARKER
from dgentic.schemas import PermissionMode
from dgentic.settings import get_settings


@pytest.fixture()
def isolated_tool_api_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    reset_database_state()
    yield root_dir
    reset_database_state()
    get_settings.cache_clear()


def test_health_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "DGentic"


def test_task_plan_contains_expected_execution_shape() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/tasks/plan",
        json={
            "objective": "Create a guarded task plan for indexing project memory.",
            "constraints": ["Only operate inside rootDir."],
            "acceptance_criteria": ["Plan includes validation step."],
        },
    )

    body = response.json()

    assert response.status_code == 201
    assert body["objective"] == "Create a guarded task plan for indexing project memory."
    assert body["constraints"] == ["Only operate inside rootDir."]
    assert body["acceptance_criteria"] == ["Plan includes validation step."]
    assert len(body["steps"]) == 5
    assert body["steps"][0]["id"] == "step-1"
    assert body["steps"][-1]["agent_role"] == "reviewer"


def test_plan_can_execute_deterministically() -> None:
    client = TestClient(create_app())
    plan_response = client.post(
        "/tasks/plan",
        json={"objective": "Execute the backend sprint plan safely."},
    )

    response = client.post("/tasks/execute", json=plan_response.json())
    body = response.json()

    assert response.status_code == 201
    assert body["status"] == "completed"
    assert body["plan_id"] == plan_response.json()["id"]
    assert len(body["results"]) == 5
    assert all(result["status"] == "completed" for result in body["results"])


def test_task_history_is_persisted_to_local_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    client = TestClient(create_app())

    plan_response = client.post(
        "/tasks/plan",
        json={"objective": "Persist task plans and execution history."},
    )
    run_response = client.post("/tasks/execute", json=plan_response.json())

    plans_response = client.get("/tasks/plans")
    runs_response = client.get("/tasks/runs")

    assert plan_response.status_code == 201
    assert run_response.status_code == 201
    assert plans_response.json()[-1]["id"] == plan_response.json()["id"]
    assert runs_response.json()[-1]["id"] == run_response.json()["id"]
    assert (tmp_path / "task-plans.json").exists()
    assert (tmp_path / "task-runs.json").exists()
    get_settings.cache_clear()


def test_guardrails_classify_filesystem_and_commands() -> None:
    client = TestClient(create_app())

    file_response = client.post(
        "/guardrails/filesystem",
        json={"path": "README.md", "action": "read"},
    )
    command_response = client.post(
        "/guardrails/commands",
        json={"command": "rm -rf important"},
    )

    assert file_response.status_code == 200
    assert file_response.json()["allowed"] is True
    assert command_response.status_code == 200
    assert command_response.json()["permission_mode"] == "blocked"


def test_guardrails_classify_powershell_slash_command_wrapper() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/guardrails/commands",
        json={"command": "powershell /Command Remove-Item important.txt"},
    )

    assert response.status_code == 200
    assert response.json()["permission_mode"] == "blocked"
    assert "remove-item" in response.json()["reason"]


def test_guarded_filesystem_read_write_enforces_root_dir(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", ".dgentic")
    get_settings.cache_clear()
    client = TestClient(create_app())

    write_response = client.post(
        "/filesystem/write",
        json={"path": "notes/sprint.txt", "content": "Sprint filesystem note."},
    )
    read_response = client.post(
        "/filesystem/read",
        json={"path": "notes/sprint.txt"},
    )
    outside_response = client.post(
        "/filesystem/read",
        json={"path": str(tmp_path / "outside.txt")},
    )
    delete_policy_response = client.post(
        "/guardrails/filesystem",
        json={"path": "notes/sprint.txt", "action": "delete"},
    )
    state_read_response = client.post(
        "/filesystem/read",
        json={"path": ".dgentic/cli-approval-digest.key"},
    )
    state_write_response = client.post(
        "/filesystem/write",
        json={"path": ".dgentic/cli-approval-digest.key", "content": "tamper"},
    )
    state_delete_policy_response = client.post(
        "/guardrails/filesystem",
        json={"path": ".dgentic/cli-approvals.json", "action": "delete"},
    )

    assert write_response.status_code == 200
    assert write_response.json()["bytes_written"] == len("Sprint filesystem note.")
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "Sprint filesystem note."
    assert outside_response.status_code == 403
    assert delete_policy_response.json()["permission_mode"] == "approval_required"
    assert state_read_response.status_code == 403
    assert state_write_response.status_code == 403
    assert state_delete_policy_response.json()["permission_mode"] == "blocked"
    get_settings.cache_clear()


def test_guarded_filesystem_binary_list_metadata_and_audit(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", ".dgentic")
    get_settings.cache_clear()
    client = TestClient(create_app())
    payload = bytes([0, 1, 2, 255])
    encoded = base64.b64encode(payload).decode("ascii")

    write_response = client.post(
        "/filesystem/write-binary",
        json={"path": "bin/blob.dat", "content_base64": encoded},
    )
    read_response = client.post(
        "/filesystem/read-binary",
        json={"path": "bin/blob.dat"},
    )
    metadata_response = client.post(
        "/filesystem/metadata",
        json={"path": "bin/blob.dat"},
    )
    list_response = client.post(
        "/filesystem/list",
        json={"path": "bin"},
    )
    logs_response = client.get("/logs?event_type=filesystem")

    assert write_response.status_code == 200
    assert write_response.json()["bytes_written"] == len(payload)
    assert read_response.status_code == 200
    assert base64.b64decode(read_response.json()["content_base64"]) == payload
    assert read_response.json()["bytes_read"] == len(payload)
    assert metadata_response.status_code == 200
    assert metadata_response.json()["type"] == "file"
    assert metadata_response.json()["size_bytes"] == len(payload)
    assert list_response.status_code == 200
    assert [entry["name"] for entry in list_response.json()["entries"]] == ["blob.dat"]
    assert logs_response.status_code == 200
    assert any(event["message"] == "Read guarded binary file." for event in logs_response.json())
    get_settings.cache_clear()


def test_guarded_filesystem_destructive_operations_require_approval(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", ".dgentic")
    get_settings.cache_clear()
    client = TestClient(create_app())

    delete_target = root_dir / "delete-me.txt"
    delete_target.write_text("remove", encoding="utf-8")
    copy_source = root_dir / "copy-source.txt"
    copy_source.write_text("copy", encoding="utf-8")
    move_source = root_dir / "move-source.txt"
    move_source.write_text("move", encoding="utf-8")
    rename_source = root_dir / "rename-source.txt"
    rename_source.write_text("rename", encoding="utf-8")

    delete_policy_response = client.post(
        "/guardrails/filesystem",
        json={"path": "delete-me.txt", "action": "delete"},
    )
    delete_without_approval = client.post(
        "/filesystem/delete",
        json={"path": "delete-me.txt"},
    )
    delete_with_approval = client.post(
        "/filesystem/delete",
        json={"path": "delete-me.txt", "approved": True},
    )
    copy_without_approval = client.post(
        "/filesystem/copy",
        json={"path": "copy-source.txt", "target_path": "copy-target.txt"},
    )
    copy_with_approval = client.post(
        "/filesystem/copy",
        json={"path": "copy-source.txt", "target_path": "copy-target.txt", "approved": True},
    )
    move_with_approval = client.post(
        "/filesystem/move",
        json={"path": "move-source.txt", "target_path": "moved.txt", "approved": True},
    )
    rename_with_approval = client.post(
        "/filesystem/rename",
        json={"path": "rename-source.txt", "new_name": "renamed.txt", "approved": True},
    )

    assert delete_policy_response.status_code == 200
    assert delete_policy_response.json()["permission_mode"] == "approval_required"
    assert delete_without_approval.status_code == 403
    assert delete_with_approval.status_code == 200
    assert not delete_target.exists()
    assert copy_without_approval.status_code == 403
    assert copy_with_approval.status_code == 200
    assert (root_dir / "copy-target.txt").read_text(encoding="utf-8") == "copy"
    assert move_with_approval.status_code == 200
    assert not move_source.exists()
    assert (root_dir / "moved.txt").read_text(encoding="utf-8") == "move"
    assert rename_with_approval.status_code == 200
    assert not rename_source.exists()
    assert (root_dir / "renamed.txt").read_text(encoding="utf-8") == "rename"
    get_settings.cache_clear()


def test_guarded_filesystem_blocks_unsafe_targets_and_symlink_escapes(
    tmp_path, monkeypatch
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside", encoding="utf-8")
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", ".dgentic")
    get_settings.cache_clear()
    client = TestClient(create_app())
    (root_dir / "source.txt").write_text("inside", encoding="utf-8")
    symlink = root_dir / "outside-link.txt"
    try:
        symlink.symlink_to(outside_file)
    except OSError as exc:
        pytest.skip(f"Symlink creation is unavailable on this platform: {exc}")

    unsafe_target_response = client.post(
        "/guardrails/filesystem",
        json={
            "path": "source.txt",
            "target_path": str(tmp_path / "outside-target.txt"),
            "action": "copy",
        },
    )
    symlink_read_response = client.post(
        "/filesystem/read",
        json={"path": "outside-link.txt"},
    )
    list_response = client.post(
        "/filesystem/list",
        json={"path": "."},
    )

    assert unsafe_target_response.status_code == 200
    assert unsafe_target_response.json()["permission_mode"] == "blocked"
    assert (
        "Target path resolves outside configured rootDir" in unsafe_target_response.json()["reason"]
    )
    assert symlink_read_response.status_code == 403
    assert [entry["name"] for entry in list_response.json()["entries"]] == ["source.txt"]
    get_settings.cache_clear()


def test_guarded_filesystem_rejects_large_payloads_and_missing_files(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", ".dgentic")
    monkeypatch.setenv("DGENTIC_MAX_FILESYSTEM_BYTES", "3")
    get_settings.cache_clear()
    client = TestClient(create_app())
    (root_dir / "large.txt").write_text("four", encoding="utf-8")

    large_write_response = client.post(
        "/filesystem/write",
        json={"path": "new-large.txt", "content": "four"},
    )
    large_read_response = client.post(
        "/filesystem/read",
        json={"path": "large.txt"},
    )
    missing_metadata_response = client.post(
        "/filesystem/metadata",
        json={"path": "missing.txt"},
    )

    assert large_write_response.status_code == 413
    assert large_read_response.status_code == 413
    assert missing_metadata_response.status_code == 404
    get_settings.cache_clear()


def test_provider_routing_prefers_local_when_privacy_is_required() -> None:
    client = TestClient(create_app())

    providers_response = client.get("/providers")
    route_response = client.post("/routing/decide", json={"privacy_required": True})

    assert providers_response.status_code == 200
    assert len(providers_response.json()) >= 2
    assert {provider["id"] for provider in providers_response.json()} >= {"ollama", "lm-studio"}
    assert route_response.status_code == 200
    assert route_response.json()["provider_id"] in {"ollama", "lm-studio"}
    assert route_response.json()["candidate_scores"]


def test_guarded_cli_execution_requires_policy_approval(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    safe_response = client.post(
        "/cli/execute",
        json={"command": "cmd /c echo hello", "timeout_seconds": 5},
    )
    approval_response = client.post(
        "/cli/execute",
        json={"command": "git status", "timeout_seconds": 5},
    )
    blocked_response = client.post(
        "/cli/execute",
        json={"command": "rm -rf important", "timeout_seconds": 5},
    )

    assert safe_response.status_code == 200
    assert safe_response.json()["exit_code"] == 0
    assert "hello" in safe_response.json()["stdout"]
    assert approval_response.status_code == 403
    assert blocked_response.status_code == 403
    get_settings.cache_clear()


def test_cli_approval_api_persists_and_executes_approved_command(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={"command": "python --version", "timeout_seconds": 10},
    )
    approval_id = create_response.json()["id"]
    list_response = client.get("/cli/approvals?status=pending")
    review_response = client.get(f"/cli/approvals/{approval_id}/review")
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer", "reason": "Safe version check."},
    )
    approved_review_response = client.get(f"/cli/approvals/{approval_id}/review")
    execute_response = client.post(f"/cli/approvals/{approval_id}/execute")
    runs_response = client.get("/cli/runs")

    assert create_response.status_code == 201
    assert create_response.json()["requested_by"] == "tester"
    assert list_response.status_code == 200
    assert any(item["id"] == approval_id for item in list_response.json())
    assert review_response.status_code == 200
    assert review_response.json()["review_command"] == "python --version"
    assert review_response.json()["policy_reason"]
    assert review_response.json()["direct_execute_available"] is False
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert approve_response.json()["decision_reason"] == "Safe version check."
    assert approved_review_response.status_code == 200
    assert approved_review_response.json()["direct_execute_available"] is True
    assert approved_review_response.json()["decision_reason"] == "Safe version check."
    assert execute_response.status_code == 200
    assert execute_response.json()["exit_code"] == 0
    assert runs_response.status_code == 200
    assert any(run["approval_id"] == approval_id for run in runs_response.json())
    get_settings.cache_clear()


def test_cli_approval_api_uses_authenticated_principal_as_reviewer(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    token = "cli-review-token"
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=cli")
    get_settings.cache_clear()
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={"command": "python --version", "timeout_seconds": 10},
        headers=headers,
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "spoofed-reviewer"},
        headers=headers,
    )

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert approve_response.json()["decided_by"] == sha256(token.encode("utf-8")).hexdigest()[:12]
    get_settings.cache_clear()


def test_cli_approval_review_api_returns_safe_bound_execution_contract(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={
            "command": "python deploy.py --token super-secret",
            "environment": {"DGENTIC_TEST_FLAG": "should-not-persist"},
            "timeout_seconds": 10,
            "agent_role": "developer",
            "agent_id": "agent-dev-1",
            "task_id": "BL-003b",
        },
    )
    approval_id = create_response.json()["id"]

    review_response = client.get(f"/cli/approvals/{approval_id}/review")

    assert create_response.status_code == 201
    assert review_response.status_code == 200
    body = review_response.json()
    assert body["review_command"] == "python deploy.py --token [REDACTED]"
    assert body["environment_keys"] == ["DGENTIC_TEST_FLAG"]
    assert body["agent_role"] == "developer"
    assert body["agent_id"] == "agent-dev-1"
    assert body["task_id"] == "BL-003b"
    assert body["requires_bound_execution_request"] is True
    assert body["direct_execute_available"] is False
    assert body["command_digest"].startswith("hmac-sha256:")
    assert body["environment_digest"].startswith("hmac-sha256:")
    assert any("redacted" in warning for warning in body["review_warnings"])
    assert any("environment keys" in warning for warning in body["review_warnings"])
    serialized = review_response.text
    assert "super-secret" not in serialized
    assert "should-not-persist" not in serialized
    get_settings.cache_clear()


def test_cli_approval_api_redacts_decision_reason_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={"command": "python --version", "timeout_seconds": 10},
    )
    approval_id = create_response.json()["id"]

    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={
            "decided_by": "reviewer",
            "reason": "Approved after checking --token super-secret.",
        },
    )
    review_response = client.get(f"/cli/approvals/{approval_id}/review")

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert "--token [REDACTED]" in approve_response.json()["decision_reason"]
    assert review_response.status_code == 200
    assert "--token [REDACTED]" in review_response.json()["decision_reason"]
    assert "super-secret" not in approve_response.text
    assert "super-secret" not in review_response.text
    get_settings.cache_clear()


def test_cli_execute_api_requires_bound_approval_id_in_production(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())

    bypass_response = client.post(
        "/cli/execute",
        json={"command": "python --version", "approved": True, "timeout_seconds": 10},
    )
    create_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={"command": "python --version", "timeout_seconds": 10},
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
    )
    execute_response = client.post(
        "/cli/execute",
        json={
            "command": "python --version",
            "timeout_seconds": 10,
            "approval_id": approval_id,
            "requested_by": "tester",
        },
    )
    second_execute_response = client.post(
        "/cli/execute",
        json={
            "command": "python --version",
            "timeout_seconds": 10,
            "approval_id": approval_id,
            "requested_by": "tester",
        },
    )

    assert bypass_response.status_code == 403
    assert "approval_id" in bypass_response.json()["detail"]
    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert execute_response.status_code == 200
    assert execute_response.json()["permission_mode"] == "approval_required"
    assert second_execute_response.status_code == 403
    assert "not executable" in second_execute_response.json()["detail"]
    get_settings.cache_clear()


def test_cli_runs_api_accepts_bound_approval_id_in_production(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())

    command = "python -c \"print('async-approved')\""
    create_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={"command": command, "timeout_seconds": 10},
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
    )
    start_response = client.post(
        "/cli/runs",
        json={
            "command": command,
            "timeout_seconds": 10,
            "approval_id": approval_id,
            "requested_by": "tester",
        },
    )
    run_id = start_response.json()["id"]

    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert start_response.status_code == 202
    assert start_response.json()["approval_id"] == approval_id

    for _attempt in range(40):
        final_response = client.get(f"/cli/runs/{run_id}")
        if final_response.json()["completed_at"] is not None:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Approved API command run did not finalize.")

    assert final_response.json()["status"] == "completed"
    assert "async-approved" in final_response.json()["stdout"]
    get_settings.cache_clear()


def test_cli_policy_rule_api_persists_and_controls_command_decisions(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/policy/rules",
        json={
            "name": "Block unsafe flag",
            "match_type": "argument_contains",
            "pattern": "--unsafe",
            "permission_mode": "blocked",
            "reason": "Unsafe flag is blocked by workspace policy.",
            "priority": 5,
        },
    )
    rule_id = create_response.json()["id"]
    decision_response = client.post(
        "/guardrails/commands",
        json={"command": "cmd /c echo --unsafe"},
    )
    list_response = client.get("/cli/policy/rules")
    update_response = client.patch(
        f"/cli/policy/rules/{rule_id}",
        json={"enabled": False},
    )
    disabled_decision_response = client.post(
        "/guardrails/commands",
        json={"command": "cmd /c echo --unsafe"},
    )

    assert create_response.status_code == 201
    assert decision_response.status_code == 200
    assert decision_response.json()["permission_mode"] == "blocked"
    assert decision_response.json()["matched_rule_id"] == rule_id
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == rule_id
    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False
    assert disabled_decision_response.json()["permission_mode"] == "autopilot_safe"
    get_settings.cache_clear()


def test_cli_async_run_api_polls_and_cancels(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    start_response = client.post(
        "/cli/runs",
        json={
            "command": 'python -c "import time; time.sleep(10)"',
            "approved": True,
            "timeout_seconds": 30,
        },
    )
    run_id = start_response.json()["id"]
    poll_response = client.get(f"/cli/runs/{run_id}")
    cancel_response = client.post(f"/cli/runs/{run_id}/cancel")

    assert start_response.status_code == 202
    assert start_response.json()["status"] == "running"
    assert poll_response.status_code == 200
    assert poll_response.json()["id"] == run_id
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    for _attempt in range(40):
        final_response = client.get(f"/cli/runs/{run_id}")
        if final_response.json()["completed_at"] is not None:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Cancelled API command did not finalize.")

    assert final_response.json()["status"] == "cancelled"
    get_settings.cache_clear()


def test_cli_cancel_orphaned_run_after_restart_returns_stale(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    run = CommandRun(
        id="cmdrun-api-orphaned",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=999999,
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    cli_runtime_service._runs.upsert(run)

    cancel_response = client.post(f"/cli/runs/{run.id}/cancel")

    assert cancel_response.status_code == 200
    body = cancel_response.json()
    assert body["status"] == "stale"
    assert body["stale_reason"] is not None
    assert "Cancellation requested" in body["stale_reason"]
    assert body["termination_status"] == "skipped"
    assert "process identity was not persisted" in body["termination_reason"]
    get_settings.cache_clear()


def test_cli_cancel_matching_orphaned_run_returns_termination_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    run = CommandRun(
        id="cmdrun-api-matching-orphan",
        command="python --version",
        cwd=root_dir.resolve(),
        status=CommandRunStatus.running,
        process_id=4242,
        process_group_id=4242,
        process_identity="posix-proc-start:match",
        permission_mode=PermissionMode.approval_required,
        duration_ms=0,
        supervisor_id="cli-supervisor-previous",
        supervisor_pid=12345,
        started_at=datetime.now(UTC),
    )
    cli_runtime_service._runs.upsert(run)
    terminated: list[str] = []
    monkeypatch.setattr(
        "dgentic.cli_runtime._process_snapshot",
        lambda pid: ProcessSnapshot(pid=pid, identity="posix-proc-start:match"),
    )
    monkeypatch.setattr(
        cli_runtime_service,
        "_terminate_orphaned_process",
        lambda orphaned_run: terminated.append(orphaned_run.id),
    )

    cancel_response = client.post(f"/cli/runs/{run.id}/cancel")

    assert cancel_response.status_code == 200
    body = cancel_response.json()
    assert terminated == [run.id]
    assert body["status"] == "stale"
    assert body["termination_status"] == "terminated"
    assert body["termination_attempted_at"] is not None
    assert body["termination_completed_at"] is not None
    assert body["terminated_by_supervisor_id"] == cli_runtime_service.supervisor_id
    get_settings.cache_clear()


def test_cli_async_run_api_times_out_and_returns_timeout_output(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    start_response = client.post(
        "/cli/runs",
        json={
            "command": 'python -c "import time; time.sleep(5)"',
            "approved": True,
            "timeout_seconds": 1,
        },
    )
    run_id = start_response.json()["id"]

    for _attempt in range(60):
        run_response = client.get(f"/cli/runs/{run_id}")
        if run_response.json()["status"] == "timed_out":
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Async API command did not time out.")

    output_response = client.get(f"/cli/runs/{run_id}/output")

    assert run_response.status_code == 200
    assert run_response.json()["status_reason"] == "Command process timed out."
    assert output_response.status_code == 200
    assert any("timed out" in chunk["text"] for chunk in output_response.json()["chunks"])
    get_settings.cache_clear()


def test_cli_async_run_output_api_returns_redacted_chunks(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    start_response = client.post(
        "/cli/runs",
        json={
            "command": (
                "python -c \"import time; print('TOKEN=abc123', flush=True); "
                "time.sleep(0.5); print('done', flush=True)\""
            ),
            "approved": True,
            "timeout_seconds": 5,
        },
    )
    run_id = start_response.json()["id"]

    for _attempt in range(40):
        output_response = client.get(f"/cli/runs/{run_id}/output")
        assert output_response.status_code == 200
        if output_response.json()["chunks"]:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Async API command did not expose output chunks.")

    body = output_response.json()
    assert body["run_id"] == run_id
    assert body["next_sequence"] >= 1
    assert any("TOKEN=[REDACTED]" in chunk["text"] for chunk in body["chunks"])
    assert all("abc123" not in chunk["text"] for chunk in body["chunks"])

    after_response = client.get(
        f"/cli/runs/{run_id}/output",
        params={"after_sequence": body["next_sequence"]},
    )
    assert after_response.status_code == 200
    assert all(
        chunk["sequence"] > body["next_sequence"] for chunk in after_response.json()["chunks"]
    )
    get_settings.cache_clear()


def test_cli_execute_api_records_context_and_environment_keys(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/cli/execute",
        json={
            "command": "cmd /c echo context",
            "requested_by": "pm",
            "agent_id": "agent-dev-1",
            "agent_role": "developer",
            "task_id": "story-5.3",
            "environment": {"DGENTIC_TEST_FLAG": "enabled"},
        },
    )
    runs_response = client.get("/cli/runs")

    assert response.status_code == 200
    assert response.json()["requested_by"] == "pm"
    assert response.json()["agent_id"] == "agent-dev-1"
    assert response.json()["agent_role"] == "developer"
    assert response.json()["task_id"] == "story-5.3"
    assert response.json()["environment_keys"] == ["DGENTIC_TEST_FLAG"]
    latest_run = runs_response.json()[-1]
    assert latest_run["environment_keys"] == ["DGENTIC_TEST_FLAG"]
    assert latest_run["agent_role"] == "developer"
    get_settings.cache_clear()


def test_cli_execute_api_blocks_out_of_root_read_only_arguments(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/cli/execute",
        json={"command": "cat ../secret.txt", "timeout_seconds": 5},
    )

    assert response.status_code == 403
    assert "outside configured rootDir" in response.json()["detail"]
    get_settings.cache_clear()


def test_cli_execute_api_rejects_blocked_environment_override(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/cli/execute",
        json={
            "command": "cmd /c echo blocked",
            "environment": {"PATH": "C:\\unsafe"},
        },
    )

    assert response.status_code == 400
    assert "PATH" in response.json()["detail"]
    get_settings.cache_clear()


def test_agent_memory_tool_and_session_registries() -> None:
    client = TestClient(create_app())

    agent_response = client.post(
        "/agents",
        json={
            "role": "researcher",
            "task": "Inspect provider contracts.",
            "expected_output": "Concise findings.",
        },
    )
    memory_response = client.post(
        "/memory",
        json={
            "title": "Guardrail decision",
            "content": "Filesystem access must stay inside rootDir.",
            "tags": ["guardrails"],
        },
    )
    search_response = client.post(
        "/memory/search",
        json={"text": "Filesystem", "tags": ["guardrails"]},
    )
    tool_response = client.post(
        "/tools",
        json={
            "name": "example-tool",
            "description": "Example local tool manifest.",
            "entrypoint": "localmcp/example-tool/main.py",
            "permission_mode": "approval_required",
        },
    )
    summary_response = client.post(
        "/sessions/summary",
        json={
            "actions": ["Added MVP sprint APIs."],
            "decisions": ["Keep provider adapters as placeholders."],
            "next_steps": ["Replace in-memory stores with persistence."],
        },
    )

    assert agent_response.status_code == 201
    assert agent_response.json()["status"] == "running"
    assert memory_response.status_code == 201
    assert search_response.status_code == 200
    assert search_response.json()[0]["record"]["title"] == "Guardrail decision"
    assert tool_response.status_code == 201
    assert summary_response.status_code == 201


def test_metadata_index_api_crud(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "memory-1",
            "tags": ["sprint", "metadata"],
            "category": "planning",
            "description": "Sprint metadata record.",
            "relevance_score": 0.8,
        },
    )
    metadata = create_response.json()
    get_response = client.get(f"/api/v1/memory/metadata/{metadata['id']}")
    list_response = client.get("/api/v1/memory/metadata?category=planning")
    patch_response = client.patch(
        f"/api/v1/memory/metadata/{metadata['id']}",
        json={"relevance_score": 0.9},
    )
    delete_response = client.delete(f"/api/v1/memory/metadata/{metadata['id']}")

    assert create_response.status_code == 201
    assert metadata["entity_id"] == "memory-1"
    assert get_response.status_code == 200
    assert get_response.json()["access_count"] == 1
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert patch_response.status_code == 200
    assert patch_response.json()["relevance_score"] == 0.9
    assert delete_response.status_code == 204
    get_settings.cache_clear()


def test_hybrid_retrieval_api_uses_default_hash_embedding(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "semantic-memory",
            "tags": ["semantic", "metadata"],
            "category": "retrieval",
            "description": "Semantic metadata retrieval combines search tags and scoring.",
            "relevance_score": 0.8,
        },
    )
    client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "release-memory",
            "tags": ["release"],
            "category": "release",
            "description": "Release packaging and checksum upload.",
            "relevance_score": 0.9,
        },
    )
    retrieval_response = client.post(
        "/api/v1/memory/retrieve/hybrid",
        json={
            "query": "semantic metadata retrieval",
            "tags": ["semantic"],
            "similarity_threshold": 0.1,
        },
    )

    assert create_response.status_code == 201
    assert retrieval_response.status_code == 200
    body = retrieval_response.json()
    assert body["total"] == 1
    assert body["results"][0]["entity_id"] == "semantic-memory"
    assert body["results"][0]["source"] == "hybrid_retrieval"
    get_settings.cache_clear()


def test_tool_registry_api_duplicate_usage_and_deprecation(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/api/v1/tools/registry",
        json={
            "tool_name": "example-tool",
            "version": "1.0.0",
            "source_path": "localmcp/example-tool",
            "interface_signature": "sha256:example",
            "permission_level": "approval_required",
            "tags": ["example"],
        },
    )
    tool = create_response.json()
    duplicate_response = client.post(
        "/api/v1/tools/registry/check-duplicate",
        json={
            "tool_name": "example-tool",
            "interface_signature": "sha256:example",
        },
    )
    usage_response = client.post(
        f"/api/v1/tools/registry/{tool['id']}/usage",
        json={"status": "success", "execution_time_ms": 25},
    )
    deprecate_response = client.post(f"/api/v1/tools/registry/{tool['id']}/deprecate")

    assert create_response.status_code == 201
    assert tool["tool_name"] == "example-tool"
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["is_duplicate"] is True
    assert usage_response.status_code == 200
    assert usage_response.json()["usage_count"] == 1
    assert usage_response.json()["reliability_score"] == 1.0
    assert deprecate_response.status_code == 200
    assert deprecate_response.json()["deprecated"] is True
    get_settings.cache_clear()


def test_agent_lifecycle_tracks_parent_child_and_completion(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    parent_response = client.post(
        "/agents",
        json={
            "role": "planner",
            "task": "Coordinate implementation.",
            "expected_output": "Work plan.",
        },
    )
    parent_id = parent_response.json()["id"]
    child_response = client.post(
        "/agents",
        json={
            "role": "worker",
            "task": "Implement a bounded slice.",
            "parent_agent_id": parent_id,
            "expected_output": "Changed files and tests.",
        },
    )
    status_response = client.patch(
        f"/agents/{child_response.json()['id']}/status",
        json={"status": "completed", "note": "Finished implementation."},
    )
    children_response = client.get(f"/agents/{parent_id}/children")

    assert parent_response.status_code == 201
    assert child_response.status_code == 201
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["completed_at"] is not None
    assert children_response.status_code == 200
    assert children_response.json()[0]["parent_agent_id"] == parent_id
    get_settings.cache_clear()


def test_dynamic_tool_generation_creates_localmcp_files_and_registry(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/tools/generate",
        json={
            "name": "pdf-generator",
            "description": "Generate a PDF from structured input.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "tags": ["pdf", "document"],
            "interface": {"input": "dict", "output": "pdf_path"},
            "dependency_paths": ["deps"],
        },
    )
    duplicate_response = client.post(
        "/tools/generate",
        json={
            "name": "pdf-generator",
            "description": "Generate a PDF from structured input.",
            "trigger_source": "sub_agent",
            "permission_mode": "approval_required",
            "tags": ["pdf"],
        },
    )
    tools_response = client.get("/tools")
    memory_response = client.post("/memory/search", json={"tags": ["localmcp"]})

    assert response.status_code == 201
    body = response.json()
    assert body["manifest"]["name"] == "pdf-generator"
    assert body["manifest"]["status"] == "active"
    assert body["manifest"]["usage_count"] == 0
    assert body["manifest"]["dependency_paths"] == ["deps"]
    assert (root_dir / "localmcp" / "pdf-generator" / "tool.py").exists()
    assert (root_dir / "localmcp" / "pdf-generator" / "wrapper.py").exists()
    assert (root_dir / "localmcp" / "pdf-generator" / "manifest.json").exists()
    assert (root_dir / "localmcp" / "pdf-generator" / "README.md").exists()
    manifest_json = json.loads(
        (root_dir / "localmcp" / "pdf-generator" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_json["dependency_paths"] == ["deps"]
    assert duplicate_response.status_code == 409
    assert any(tool["name"] == "pdf-generator" for tool in tools_response.json())
    assert any(
        result["record"]["title"] == "Generated tool: pdf-generator"
        for result in memory_response.json()
    )
    get_settings.cache_clear()


def test_dynamic_tool_generation_registers_sql_registry_row(
    isolated_tool_api_state,
) -> None:
    root_dir = isolated_tool_api_state
    client = TestClient(create_app())
    interface = {"input": {"text": "str"}, "output": "summary"}

    response = client.post(
        "/tools/generate",
        json={
            "name": "sql-registered-tool",
            "version": "1.2.3",
            "description": "Summarize text using a generated local tool.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "tags": ["summary", "qa"],
            "interface": interface,
        },
    )
    registry_response = client.get("/api/v1/tools/registry?permission_level=autopilot_safe")
    duplicate_response = client.post(
        "/api/v1/tools/registry/check-duplicate",
        json={
            "tool_name": "other-summary-tool",
            "interface_signature": _interface_signature(interface),
        },
    )

    assert response.status_code == 201
    assert (root_dir / "localmcp" / "sql-registered-tool" / "tool.py").exists()
    assert registry_response.status_code == 200
    registry_items = registry_response.json()["items"]
    registry_tool = next(
        item for item in registry_items if item["tool_name"] == "sql-registered-tool"
    )
    assert registry_tool["version"] == "1.2.3"
    assert registry_tool["source_path"].replace("\\", "/") == (
        "localmcp/sql-registered-tool/tool.py"
    )
    assert registry_tool["permission_level"] == "autopilot_safe"
    assert set(registry_tool["tags"]) >= {"summary", "qa", "main_agent"}
    assert registry_tool["description"] == "Summarize text using a generated local tool."
    assert registry_tool["created_by_agent"] == "main_agent"
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["is_duplicate"] is True
    assert any(
        item["tool_name"] == "sql-registered-tool"
        for item in duplicate_response.json()["similar_tools"]
    )


def test_dynamic_tool_generation_sql_duplicate_prevents_file_writes(
    isolated_tool_api_state,
) -> None:
    root_dir = isolated_tool_api_state
    client = TestClient(create_app())
    interface = {"input": "dict", "output": {"path": "str"}}

    registry_response = client.post(
        "/api/v1/tools/registry",
        json={
            "tool_name": "existing-sql-tool",
            "version": "9.9.9",
            "source_path": "localmcp/existing-sql-tool/tool.py",
            "interface_signature": _interface_signature(interface),
            "permission_level": "autopilot_safe",
            "tags": ["document"],
        },
    )
    response = client.post(
        "/tools/generate",
        json={
            "name": "new-tool-with-existing-interface",
            "description": "Should be blocked by SQL registry duplicate detection.",
            "trigger_source": "skill",
            "permission_mode": "autopilot_safe",
            "tags": ["document"],
            "interface": interface,
        },
    )

    assert registry_response.status_code == 201
    assert response.status_code == 409
    assert not (root_dir / "localmcp" / "new-tool-with-existing-interface").exists()


def test_dynamic_tool_generation_blocks_invalid_permission_and_deprecates_tool(
    tmp_path, monkeypatch
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    blocked_response = client.post(
        "/tools/generate",
        json={
            "name": "blocked-tool",
            "description": "Should not be generated.",
            "trigger_source": "skill",
            "permission_mode": "blocked",
        },
    )
    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "summarizer",
            "description": "Summarize text payloads.",
            "trigger_source": "skill",
            "permission_mode": "autopilot_safe",
        },
    )
    governance_response = client.patch(
        "/tools/summarizer/governance",
        json={"status": "deprecated", "reason": "Replaced by a better version."},
    )

    assert blocked_response.status_code == 403
    assert generate_response.status_code == 201
    assert governance_response.status_code == 200
    assert governance_response.json()["status"] == "deprecated"
    assert governance_response.json()["deprecated_reason"] == "Replaced by a better version."
    get_settings.cache_clear()


def test_generated_tool_execute_api_updates_reliability(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "echo-tool",
            "description": "Echo payloads.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
        },
    )
    execute_response = client.post(
        "/tools/echo-tool/execute",
        json={"payload": {"value": 42}},
    )
    tools_response = client.get("/tools")

    assert generate_response.status_code == 201
    assert execute_response.status_code == 200
    assert execute_response.json()["exit_code"] == 0
    assert execute_response.json()["parsed_output"]["payload"] == {"value": 42}
    stored = next(tool for tool in tools_response.json() if tool["name"] == "echo-tool")
    assert stored["usage_count"] == 1
    assert stored["success_count"] == 1
    assert stored["reliability_score"] == 1.0
    get_settings.cache_clear()


def test_generated_tool_execute_api_requires_bound_approval_in_production(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    get_settings.cache_clear()
    client = TestClient(create_app())

    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-approval-tool",
            "description": "Requires a bound tool approval.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": (
                "def run(payload):\n    return {'ok': True, 'value': payload.get('value')}\n"
            ),
        },
    )
    bypass_response = client.post(
        "/tools/api-approval-tool/execute",
        json={"payload": {"value": "safe"}, "approved": True, "timeout_seconds": 5},
    )
    create_response = client.post(
        "/tools/api-approval-tool/approvals?requested_by=tester",
        json={
            "payload": {"value": "PASSWORD=api-approval-secret"},
            "timeout_seconds": 5,
            "agent_role": "developer",
            "task_id": "sprint-11",
        },
    )
    approval_id = create_response.json()["id"]
    list_response = client.get("/tools/approvals?status=pending")
    review_response = client.get(f"/tools/approvals/{approval_id}/review")
    approve_response = client.post(
        f"/tools/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer", "reason": "Approved with --token api-reason-secret."},
    )
    mismatch_response = client.post(
        "/tools/api-approval-tool/execute",
        json={
            "payload": {"value": "different"},
            "approval_id": approval_id,
            "timeout_seconds": 5,
            "requested_by": "tester",
            "agent_role": "developer",
            "task_id": "sprint-11",
        },
    )
    execute_response = client.post(
        "/tools/api-approval-tool/execute",
        json={
            "payload": {"value": "PASSWORD=api-approval-secret"},
            "approval_id": approval_id,
            "timeout_seconds": 5,
            "requested_by": "tester",
            "agent_role": "developer",
            "task_id": "sprint-11",
        },
    )
    second_execute_response = client.post(
        "/tools/api-approval-tool/execute",
        json={
            "payload": {"value": "PASSWORD=api-approval-secret"},
            "approval_id": approval_id,
            "timeout_seconds": 5,
            "requested_by": "tester",
            "agent_role": "developer",
            "task_id": "sprint-11",
        },
    )

    assert generate_response.status_code == 201
    assert bypass_response.status_code == 403
    assert "approval_id" in bypass_response.json()["detail"]
    assert create_response.status_code == 201
    assert create_response.json()["review_payload"]["value"] == "PASSWORD=[REDACTED]"
    assert "api-approval-secret" not in create_response.text
    assert list_response.status_code == 200
    assert any(item["id"] == approval_id for item in list_response.json())
    assert review_response.status_code == 200
    assert review_response.json()["review_payload"]["value"] == "PASSWORD=[REDACTED]"
    assert review_response.json()["direct_execute_available"] is False
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert "--token [REDACTED]" in approve_response.json()["decision_reason"]
    assert "api-reason-secret" not in approve_response.text
    assert mismatch_response.status_code == 403
    assert "not bound" in mismatch_response.json()["detail"]
    assert execute_response.status_code == 200
    assert execute_response.json()["approval_id"] == approval_id
    assert execute_response.json()["parsed_output"]["value"] == "PASSWORD=[REDACTED]"
    assert second_execute_response.status_code == 403
    assert "not executable" in second_execute_response.json()["detail"]
    get_settings.cache_clear()


def test_tool_approval_approve_api_requires_approvals_capability(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "true")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        "tool-token=tools;approval-token=approvals",
    )
    get_settings.cache_clear()
    client = TestClient(create_app())
    tool_headers = {"Authorization": "Bearer tool-token"}
    approval_headers = {"Authorization": "Bearer approval-token"}

    generate_response = client.post(
        "/tools/generate",
        headers=tool_headers,
        json={
            "name": "api-review-boundary-tool",
            "description": "Requires separate approval capability.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": "def run(payload):\n    return {'ok': True}\n",
        },
    )
    create_response = client.post(
        "/tools/api-review-boundary-tool/approvals?requested_by=tester",
        headers=tool_headers,
        json={"payload": {}, "timeout_seconds": 5},
    )
    approval_id = create_response.json()["id"]
    tool_approve_response = client.post(
        f"/tools/approvals/{approval_id}/approve",
        headers=tool_headers,
        json={"decided_by": "spoofed-reviewer"},
    )
    approval_approve_response = client.post(
        f"/tools/approvals/{approval_id}/approve",
        headers=approval_headers,
        json={"decided_by": "spoofed-reviewer"},
    )

    assert generate_response.status_code == 201
    assert create_response.status_code == 201
    assert tool_approve_response.status_code == 403
    assert approval_approve_response.status_code == 200
    assert (
        approval_approve_response.json()["decided_by"] == sha256(b"approval-token").hexdigest()[:12]
    )
    get_settings.cache_clear()


def test_generated_tool_execute_api_redacts_secret_outputs_and_audits(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    raw_secrets = [
        "api-printed-token-secret",
        "api-stderr-password-secret",
        "api-json-stderr-token-secret",
        "api-json-stderr-password-secret",
        "api-colon-key-secret",
        "api-auth-header-secret",
        "api-basic-auth-secret",
        "api-token-auth-secret",
        "api-proxy-auth-secret",
        "api-returned-token-secret",
        "api-returned-secret",
        "api-returned-key-secret",
        "api-returned-password-secret",
    ]

    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-redacting-tool",
            "description": "Return and print secret-shaped values.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": (
                "import sys\n\n"
                "def run(payload):\n"
                "    print('TOKEN=api-printed-token-secret')\n"
                "    sys.stderr.write('PASSWORD=api-stderr-password-secret\\n')\n"
                '    sys.stderr.write(\'{"token":"api-json-stderr-token-secret",'
                '"nested":{"password":"api-json-stderr-password-secret"}}\\n\')\n'
                "    sys.stderr.write('api_key: api-colon-key-secret\\n')\n"
                "    sys.stderr.write('Authorization: Bearer api-auth-header-secret\\n')\n"
                "    sys.stderr.write('Authorization: Basic api-basic-auth-secret\\n')\n"
                "    sys.stderr.write('authorization: token api-token-auth-secret\\n')\n"
                "    sys.stderr.write('Proxy-Authorization: ApiKey api-proxy-auth-secret\\n')\n"
                "    return {\n"
                "        'token': 'api-returned-token-secret',\n"
                "        'payload': 'SECRET=api-returned-secret "
                "--api-key api-returned-key-secret',\n"
                "        'nested': {'password': 'api-returned-password-secret'},\n"
                "        'safe': 'visible',\n"
                "    }\n"
            ),
        },
    )
    assert generate_response.status_code == 201
    logs_before_response = client.get("/logs?event_type=tool")

    execute_response = client.post(
        "/tools/api-redacting-tool/execute",
        json={"payload": {"value": 42}},
    )
    logs_after_response = client.get("/logs?event_type=tool")

    assert logs_before_response.status_code == 200
    assert execute_response.status_code == 200
    assert logs_after_response.status_code == 200
    body = execute_response.json()
    assert body["exit_code"] == 0
    assert json.loads(body["stdout"])["token"] == REDACTED_SECRET_MARKER
    assert "TOKEN=[REDACTED]" in body["stderr"]
    assert "Authorization: Bearer [REDACTED]" in body["stderr"]
    assert "Authorization: Basic [REDACTED]" in body["stderr"]
    assert "authorization: token [REDACTED]" in body["stderr"]
    assert "Proxy-Authorization: ApiKey [REDACTED]" in body["stderr"]
    assert body["stderr"].count(REDACTED_SECRET_MARKER) >= 9
    assert body["parsed_output"]["token"] == REDACTED_SECRET_MARKER
    assert body["parsed_output"]["nested"]["password"] == REDACTED_SECRET_MARKER
    assert body["parsed_output"]["safe"] == "visible"
    assert REDACTED_SECRET_MARKER in body["parsed_output"]["payload"]
    for raw_secret in raw_secrets:
        assert raw_secret not in execute_response.text

    logs_before = logs_before_response.json()
    new_events = logs_after_response.json()[len(logs_before) :]
    execution_events = [
        event for event in new_events if event["subject_id"] == "api-redacting-tool"
    ]
    assert execution_events
    execution_event = execution_events[-1]
    assert execution_event["event_type"] == "tool"
    assert execution_event["metadata"]["exit_code"] == 0
    serialized_event = json.dumps(execution_event, sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_event
    get_settings.cache_clear()


def test_generated_tool_execute_api_redacts_failed_tool_secret_outputs_and_audits(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    raw_secrets = [
        "api-failure-json-secret",
        "api-failure-password-secret",
        "api-failure-auth-secret",
        "api-failure-exception-secret",
    ]

    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-failing-redacting-tool",
            "description": "Fail after logging secret-shaped values.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": (
                "import sys\n\n"
                "def run(payload):\n"
                '    sys.stderr.write(\'{"token":"api-failure-json-secret",'
                '"nested":{"password":"api-failure-password-secret"}}\\n\')\n'
                "    sys.stderr.write('Authorization: Bearer api-failure-auth-secret\\n')\n"
                "    raise RuntimeError('PASSWORD=api-failure-exception-secret')\n"
            ),
        },
    )
    assert generate_response.status_code == 201
    logs_before_response = client.get("/logs?event_type=tool")

    execute_response = client.post(
        "/tools/api-failing-redacting-tool/execute",
        json={"payload": {"value": 42}},
    )
    logs_after_response = client.get("/logs?event_type=tool")

    assert logs_before_response.status_code == 200
    assert execute_response.status_code == 200
    assert logs_after_response.status_code == 200
    body = execute_response.json()
    assert body["exit_code"] == 1
    assert body["stdout"] == ""
    assert body["parsed_output"] is None
    assert "Authorization: Bearer [REDACTED]" in body["stderr"]
    assert "RuntimeError: PASSWORD=[REDACTED]" in body["stderr"]
    for raw_secret in raw_secrets:
        assert raw_secret not in execute_response.text

    logs_before = logs_before_response.json()
    new_events = logs_after_response.json()[len(logs_before) :]
    execution_events = [
        event for event in new_events if event["subject_id"] == "api-failing-redacting-tool"
    ]
    assert execution_events
    execution_event = execution_events[-1]
    assert execution_event["event_type"] == "tool"
    assert execution_event["metadata"]["exit_code"] == 1
    serialized_event = json.dumps(execution_event, sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_event
    get_settings.cache_clear()


def test_generated_tool_execute_api_redacts_timed_out_tool_outputs_and_audits(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    raw_secrets = [
        "api-timeout-token-secret",
        "api-timeout-password-secret",
        "api-timeout-auth-secret",
    ]

    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-timeout-redacting-tool",
            "description": "Timeout after logging secret-shaped values.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": (
                "import sys\n"
                "import time\n\n"
                "def run(payload):\n"
                '    sys.stderr.write(\'{"token":"api-timeout-token-secret",'
                '"nested":{"password":"api-timeout-password-secret"}}\\n\')\n'
                "    sys.stderr.write('Authorization: Bearer api-timeout-auth-secret\\n')\n"
                "    sys.stderr.flush()\n"
                "    time.sleep(5)\n"
                "    return {'ok': True}\n"
            ),
        },
    )
    assert generate_response.status_code == 201
    logs_before_response = client.get("/logs?event_type=tool")

    execute_response = client.post(
        "/tools/api-timeout-redacting-tool/execute",
        json={"payload": {"value": 42}, "timeout_seconds": 1},
    )
    logs_after_response = client.get("/logs?event_type=tool")

    assert logs_before_response.status_code == 200
    assert execute_response.status_code == 200
    assert logs_after_response.status_code == 200
    body = execute_response.json()
    assert body["exit_code"] == -1
    assert body["parsed_output"] is None
    assert "Authorization: Bearer [REDACTED]" in body["stderr"]
    assert "Tool timed out after 1 seconds." in body["stderr"]
    for raw_secret in raw_secrets:
        assert raw_secret not in execute_response.text

    logs_before = logs_before_response.json()
    new_events = logs_after_response.json()[len(logs_before) :]
    execution_events = [
        event for event in new_events if event["subject_id"] == "api-timeout-redacting-tool"
    ]
    assert execution_events
    execution_event = execution_events[-1]
    assert execution_event["event_type"] == "tool"
    assert execution_event["metadata"]["exit_code"] == -1
    serialized_event = json.dumps(execution_event, sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in serialized_event
    get_settings.cache_clear()


def test_provider_generate_api_rejects_unsupported_provider() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "unknown",
            "model": "local-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 400


def test_logs_capture_new_backend_activity() -> None:
    client = TestClient(create_app())

    client.post("/guardrails/commands", json={"command": "git status"})
    response = client.get("/logs?event_type=cli")

    assert response.status_code == 200
    assert response.json()
    assert response.json()[-1]["event_type"] == "cli"


def test_logs_redact_legacy_approval_reason_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    events_path = tmp_path / "state" / "events.json"
    events_path.parent.mkdir(parents=True)
    events_path.write_text(
        json.dumps(
            [
                {
                    "id": "event-legacy-approval-denial",
                    "event_type": "approval",
                    "message": "Denied CLI command request with --token ps` value.",
                    "actor": "reviewer TOKEN=super-secret",
                    "subject_id": "approval-legacy PASSWORD=super-secret",
                    "metadata": {
                        "reason": "Denied because PASSWORD=super-secret was pasted.",
                        "accessToken": "camel-secret",
                        "tokens": "plural-token-secret",
                        "refreshToken": "refresh-secret",
                        "clientSecret": "client-secret",
                        "api_keys": "plural-api-key-secret",
                        "passwordHash": "hash-secret",
                        "passwords": "plural-password-secret",
                        "secrets": "plural-secret-secret",
                        "access_keys": "plural-access-key-secret",
                        "secretValue": "value-secret",
                        "nested": {
                            "note": "Checked --token ps` nested first.",
                            "token": "nested-secret",
                            "credentials": {"password": "hunter2"},
                        },
                    },
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    client = TestClient(create_app())

    response = client.get("/logs?event_type=approval")

    assert response.status_code == 200
    serialized = response.text
    body = response.json()[0]
    assert "--token [REDACTED]" in body["message"]
    assert "TOKEN=[REDACTED]" in body["actor"]
    assert "PASSWORD=[REDACTED]" in body["subject_id"]
    assert "PASSWORD=[REDACTED]" in body["metadata"]["reason"]
    assert body["metadata"]["accessToken"] == "[REDACTED]"
    assert body["metadata"]["tokens"] == "[REDACTED]"
    assert body["metadata"]["refreshToken"] == "[REDACTED]"
    assert body["metadata"]["clientSecret"] == "[REDACTED]"
    assert body["metadata"]["api_keys"] == "[REDACTED]"
    assert body["metadata"]["passwordHash"] == "[REDACTED]"
    assert body["metadata"]["passwords"] == "[REDACTED]"
    assert body["metadata"]["secrets"] == "[REDACTED]"
    assert body["metadata"]["access_keys"] == "[REDACTED]"
    assert body["metadata"]["secretValue"] == "[REDACTED]"
    assert "--token [REDACTED]" in body["metadata"]["nested"]["note"]
    assert body["metadata"]["nested"]["token"] == "[REDACTED]"
    assert body["metadata"]["nested"]["credentials"] == "[REDACTED]"
    assert "super-secret" not in serialized
    assert "ps` value" not in serialized
    assert "ps` nested" not in serialized
    assert "camel-secret" not in serialized
    assert "plural-token-secret" not in serialized
    assert "refresh-secret" not in serialized
    assert "client-secret" not in serialized
    assert "plural-api-key-secret" not in serialized
    assert "hash-secret" not in serialized
    assert "plural-password-secret" not in serialized
    assert "plural-secret-secret" not in serialized
    assert "plural-access-key-secret" not in serialized
    assert "value-secret" not in serialized
    assert "nested-secret" not in serialized
    assert "hunter2" not in serialized
    get_settings.cache_clear()


def _interface_signature(interface: dict) -> str:
    payload = json.dumps(interface, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"
