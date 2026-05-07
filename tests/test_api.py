import time

from fastapi.testclient import TestClient

from dgentic.main import create_app
from dgentic.settings import get_settings


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


def test_guarded_filesystem_read_write_enforces_root_dir(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
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

    assert write_response.status_code == 200
    assert write_response.json()["bytes_written"] == len("Sprint filesystem note.")
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "Sprint filesystem note."
    assert outside_response.status_code == 403
    assert delete_policy_response.json()["permission_mode"] == "approval_required"
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
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
    )
    execute_response = client.post(f"/cli/approvals/{approval_id}/execute")
    runs_response = client.get("/cli/runs")

    assert create_response.status_code == 201
    assert create_response.json()["requested_by"] == "tester"
    assert list_response.status_code == 200
    assert any(item["id"] == approval_id for item in list_response.json())
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert execute_response.status_code == 200
    assert execute_response.json()["exit_code"] == 0
    assert runs_response.status_code == 200
    assert any(run["approval_id"] == approval_id for run in runs_response.json())
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
    assert (root_dir / "localmcp" / "pdf-generator" / "tool.py").exists()
    assert (root_dir / "localmcp" / "pdf-generator" / "wrapper.py").exists()
    assert (root_dir / "localmcp" / "pdf-generator" / "manifest.json").exists()
    assert (root_dir / "localmcp" / "pdf-generator" / "README.md").exists()
    assert duplicate_response.status_code == 409
    assert any(tool["name"] == "pdf-generator" for tool in tools_response.json())
    assert any(
        result["record"]["title"] == "Generated tool: pdf-generator"
        for result in memory_response.json()
    )
    get_settings.cache_clear()


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
