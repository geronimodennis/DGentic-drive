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
    assert route_response.status_code == 200
    assert route_response.json()["provider_id"] == "local-placeholder"


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


def test_logs_capture_new_backend_activity() -> None:
    client = TestClient(create_app())

    client.post("/guardrails/commands", json={"command": "git status"})
    response = client.get("/logs?event_type=cli")

    assert response.status_code == 200
    assert response.json()
    assert response.json()[-1]["event_type"] == "cli"
