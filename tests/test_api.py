import base64
import json
import time
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from dgentic import provider_runtime, provider_transport, providers
from dgentic.api.routes import cli_runtime_service
from dgentic.cli_runtime import CommandRun, CommandRunStatus, ProcessSnapshot
from dgentic.credentials import CredentialReferenceRequest, create_credential_reference
from dgentic.database import get_db_session, reset_database_state
from dgentic.main import create_app
from dgentic.memory.models import MemoryMetadata
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


def _configure_production_task_api_state(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        "alpha-token=tasks;beta-token=tasks;admin-token=admin",
    )
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()


def _configure_production_shared_memory_api_state(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        ("alpha-token=tasks,agents,memory;beta-token=tasks,agents,memory;admin-token=admin"),
    )
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    reset_database_state()


def test_health_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "DGentic"


@pytest.fixture(autouse=True)
def reset_provider_circuit_state_for_api():
    provider_runtime.reset_provider_circuit_state()
    yield
    provider_runtime.reset_provider_circuit_state()


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


def test_orchestration_api_lifecycle_enforces_dag_and_close_gates(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Coordinate Sprint 14 BL-008a.",
            "required_dod_evidence": ["tests", "review"],
            "tasks": [
                {
                    "id": "developer-implementation",
                    "title": "Implement orchestration control plane.",
                    "description": "Wire production orchestration behavior.",
                    "role": "Developer",
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "expected_output": "Production behavior is implemented.",
                    "validation": "Developer smoke passes.",
                },
                {
                    "id": "qa-validation",
                    "title": "Validate orchestration control plane.",
                    "description": "Add focused orchestration regressions.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_orchestration.py"],
                    "expected_output": "Focused tests cover control-plane behavior.",
                    "validation": "pytest tests/test_orchestration.py passes.",
                },
                {
                    "id": "pm-closeout",
                    "title": "Close sprint status.",
                    "description": "Record validation and closeout evidence.",
                    "role": "PM",
                    "dependencies": ["developer-implementation", "qa-validation"],
                    "declared_write_paths": ["docs/progress/project-progress-log.md"],
                    "expected_output": "Sprint status is updated.",
                    "validation": "DoD evidence is present.",
                },
            ],
        },
    )
    body = create_response.json()
    run_id = body["id"]

    assert create_response.status_code == 201
    assert set(body["scheduled_task_ids"]) == {"developer-implementation", "qa-validation"}
    assert {task["id"]: task["status"] for task in body["tasks"]} == {
        "developer-implementation": "running",
        "qa-validation": "running",
        "pm-closeout": "pending",
    }

    list_response = client.get("/tasks/orchestrations")
    get_response = client.get(f"/tasks/orchestrations/{run_id}")
    premature_close_response = client.post(
        f"/tasks/orchestrations/{run_id}/close",
        json={"evidence": {"tests": "not enough while tasks are incomplete"}},
    )
    first_done_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/developer-implementation",
        json={"status": "completed", "output": {"source": "implemented"}},
    )
    second_done_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/qa-validation",
        json={"status": "completed", "output": {"tests": "passed"}},
    )
    closeout_done_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/pm-closeout",
        json={"status": "completed", "output": {"progress": "updated"}},
    )
    missing_evidence_response = client.post(
        f"/tasks/orchestrations/{run_id}/close",
        json={"evidence": {"tests": "pytest tests/test_orchestration.py passed"}},
    )
    close_response = client.post(
        f"/tasks/orchestrations/{run_id}/close",
        json={
            "evidence": {
                "tests": "pytest tests/test_orchestration.py passed",
                "review": "Reviewer reported no blockers.",
            }
        },
    )
    closed_mutation_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/pm-closeout",
        json={"status": "failed", "error": "late mutation"},
    )

    assert list_response.status_code == 200
    assert any(run["id"] == run_id for run in list_response.json())
    assert get_response.status_code == 200
    assert get_response.json()["id"] == run_id
    assert premature_close_response.status_code == 400
    assert "incomplete tasks" in premature_close_response.json()["detail"]
    assert first_done_response.status_code == 200
    assert first_done_response.json()["scheduled_task_ids"] == []
    assert second_done_response.status_code == 200
    assert second_done_response.json()["scheduled_task_ids"] == ["pm-closeout"]
    assert closeout_done_response.status_code == 200
    assert missing_evidence_response.status_code == 400
    assert "review" in missing_evidence_response.json()["detail"]
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "completed"
    assert close_response.json()["dod_evidence"]["review"] == "Reviewer reported no blockers."
    assert closed_mutation_response.status_code == 400
    assert "closed orchestration" in closed_mutation_response.json()["detail"]


def test_orchestration_api_rejects_cycles_and_reports_role_boundary_follow_ups(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())

    cycle_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject cyclic orchestration graphs.",
            "tasks": [
                {
                    "id": "developer-implementation",
                    "title": "Implementation",
                    "description": "Implementation depends on QA.",
                    "role": "Developer",
                    "dependencies": ["qa-validation"],
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "validation": "No cycle.",
                },
                {
                    "id": "qa-validation",
                    "title": "QA",
                    "description": "QA depends on implementation.",
                    "role": "QA",
                    "dependencies": ["developer-implementation"],
                    "declared_write_paths": ["tests/test_orchestration.py"],
                    "validation": "No cycle.",
                },
            ],
        },
    )
    boundary_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Block out-of-bound QA writes.",
            "tasks": [
                {
                    "id": "qa-source-edit",
                    "title": "QA attempts source edit.",
                    "description": "QA must not modify production source.",
                    "role": "QA",
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "validation": "Boundary blocks source edit.",
                }
            ],
        },
    )
    forged_state_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject server-owned task state.",
            "tasks": [
                {
                    "id": "forged-complete",
                    "title": "Forged state",
                    "description": "Caller tries to bypass scheduling.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_orchestration.py"],
                    "status": "completed",
                    "agent_id": "agent-forged",
                    "validation": "Should be rejected.",
                }
            ],
        },
    )

    assert cycle_response.status_code == 400
    assert "acyclic" in cycle_response.json()["detail"]
    assert boundary_response.status_code == 201
    body = boundary_response.json()
    assert body["tasks"][0]["status"] == "blocked"
    assert body["blockers"][0]["severity"] == "role_boundary"
    assert body["follow_ups"][0]["assigned_role"] == "Developer"
    assert body["role_boundary_decisions"][0]["suggested_owner_role"] == "Developer"
    assert forged_state_response.status_code == 422


def test_orchestration_api_recovers_blocked_task_and_persists_state(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Recover blocked orchestration task.",
            "required_dod_evidence": ["tests"],
            "tasks": [
                {
                    "id": "qa-source-edit",
                    "title": "QA source edit",
                    "description": "QA attempts source work.",
                    "role": "QA",
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "validation": "Recovery should correct ownership.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]

    unsafe_recover_response = client.post(
        f"/tasks/orchestrations/{run_id}/tasks/qa-source-edit/recover",
        json={"resolution": "No ownership correction yet."},
    )
    recover_response = client.post(
        f"/tasks/orchestrations/{run_id}/tasks/qa-source-edit/recover",
        json={
            "resolution": "API_KEY=secret-value reassigned to Developer.",
            "role": "Developer",
            "declared_write_paths": ["src/dgentic/orchestration.py"],
            "reset_retry_count": True,
        },
    )
    persisted_response = client.get(f"/tasks/orchestrations/{run_id}")
    completed_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/qa-source-edit",
        json={"status": "completed", "output": {"source": "done"}},
    )
    close_response = client.post(
        f"/tasks/orchestrations/{run_id}/close",
        json={"evidence": {"tests": "pytest tests/test_api.py passed"}},
    )
    logs_response = client.get("/logs")

    assert create_response.status_code == 201
    assert create_response.json()["tasks"][0]["status"] == "blocked"
    assert unsafe_recover_response.status_code == 400
    assert "role-boundary validation still fails" in unsafe_recover_response.json()["detail"]
    assert recover_response.status_code == 200
    recovered = recover_response.json()
    assert recovered["blockers"] == []
    assert recovered["follow_ups"] == []
    assert recovered["scheduled_task_ids"] == ["qa-source-edit"]
    assert recovered["role_boundary_decisions"][0]["allowed"] is True
    assert recovered["tasks"][0]["status"] == "running"
    assert recovered["tasks"][0]["role"] == "Developer"
    assert recovered["tasks"][0]["declared_write_paths"] == ["src/dgentic/orchestration.py"]
    assert persisted_response.json()["tasks"][0]["status"] == "running"
    assert completed_response.status_code == 200
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "completed"
    recovery_event = next(
        event
        for event in logs_response.json()
        if event["subject_id"] == run_id
        and event["message"] == "Recovered blocked orchestration task."
    )
    assert recovery_event["metadata"]["resolution"] == "API_KEY=[REDACTED] reassigned to Developer."
    assert recovery_event["metadata"]["previous_role"] == "QA"
    assert recovery_event["metadata"]["recovered_role"] == "Developer"
    assert recovery_event["metadata"]["previous_declared_write_paths"] == [
        "src/dgentic/orchestration.py"
    ]
    assert recovery_event["metadata"]["recovered_declared_write_paths"] == [
        "src/dgentic/orchestration.py"
    ]
    assert "secret-value" not in json.dumps(recovery_event)


def test_orchestration_api_cycle_reconciles_agent_completion(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Cycle completed agent work.",
            "tasks": [
                {
                    "id": "developer-implementation",
                    "title": "Implement cycle source.",
                    "description": "Produce source changes.",
                    "role": "Developer",
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "validation": "Developer work complete.",
                },
                {
                    "id": "qa-validation",
                    "title": "Validate cycle source.",
                    "description": "Validate source changes.",
                    "role": "QA",
                    "dependencies": ["developer-implementation"],
                    "declared_write_paths": ["tests/test_orchestration.py"],
                    "validation": "QA work runs after implementation.",
                },
            ],
        },
    )
    body = create_response.json()
    run_id = body["id"]
    agent_id = body["tasks"][0]["agent_id"]

    status_response = client.patch(
        f"/agents/{agent_id}/status",
        json={"status": "completed", "note": "Source work complete."},
    )
    cycle_response = client.post(f"/tasks/orchestrations/{run_id}/cycle")
    get_response = client.get(f"/tasks/orchestrations/{run_id}")

    assert create_response.status_code == 201
    assert status_response.status_code == 200
    assert cycle_response.status_code == 200
    cycled = cycle_response.json()
    assert cycled["tasks"][0]["status"] == "completed"
    assert cycled["tasks"][0]["output"] == {
        "agent_id": agent_id,
        "agent_status": "completed",
    }
    assert cycled["scheduled_task_ids"] == ["qa-validation"]
    assert cycled["tasks"][1]["status"] == "running"
    assert cycled["tasks"][1]["agent_id"]
    assert get_response.json()["tasks"][1]["status"] == "running"


def test_orchestration_api_loop_reconciles_until_waiting_agents(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Loop completed agent work.",
            "tasks": [
                {
                    "id": "developer-implementation",
                    "title": "Implement loop source.",
                    "description": "Produce source changes.",
                    "role": "Developer",
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "validation": "Developer work complete.",
                },
                {
                    "id": "qa-validation",
                    "title": "Validate loop source.",
                    "description": "Validate source changes.",
                    "role": "QA",
                    "dependencies": ["developer-implementation"],
                    "declared_write_paths": ["tests/test_orchestration.py"],
                    "validation": "QA work runs after implementation.",
                },
            ],
        },
    )
    body = create_response.json()
    run_id = body["id"]
    agent_id = body["tasks"][0]["agent_id"]
    status_response = client.patch(
        f"/agents/{agent_id}/status",
        json={"status": "completed", "note": "Source work complete."},
    )
    loop_response = client.post(
        f"/tasks/orchestrations/{run_id}/loop",
        json={"max_iterations": 5},
    )
    default_loop_response = client.post(f"/tasks/orchestrations/{run_id}/loop")

    assert create_response.status_code == 201
    assert status_response.status_code == 200
    assert loop_response.status_code == 200
    loop = loop_response.json()
    assert loop["iterations"] == 2
    assert loop["made_progress"] is True
    assert loop["stopped_reason"] == "waiting_for_agents"
    assert loop["running_task_ids"] == ["qa-validation"]
    assert loop["unresolved_blocker_ids"] == []
    assert loop["run"]["tasks"][0]["status"] == "completed"
    assert loop["run"]["tasks"][1]["status"] == "running"
    assert default_loop_response.status_code == 200
    assert default_loop_response.json()["stopped_reason"] == "waiting_for_agents"


def test_orchestration_api_background_execution_start_poll_and_list(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Run detached orchestration from the API.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "Validate detached execution.",
                    "description": "Keep the run active until agent work completes.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Detached execution can be polled.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]

    start_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )
    execution_id = start_response.json()["id"]
    completed = _poll_api_execution(client, run_id, execution_id)
    list_response = client.get(f"/tasks/orchestrations/{run_id}/executions")

    assert create_response.status_code == 201
    assert start_response.status_code == 202
    assert start_response.json()["status"] == "starting"
    assert start_response.json()["request"]["max_iterations"] == 2
    assert "scheduler_lease_id" in start_response.json()
    assert "scheduler_lease_token" not in start_response.json()
    assert completed["status"] == "completed"
    assert "scheduler_lease_token" not in completed
    assert completed["result"]["stopped_reason"] == "waiting_for_agents"
    assert completed["result"]["running_task_ids"] == ["qa-validation"]
    assert list_response.status_code == 200
    assert [execution["id"] for execution in list_response.json()] == [execution_id]


def test_orchestration_api_background_execution_duplicate_active_returns_409(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject duplicate detached orchestration from the API.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "Validate detached duplicate rejection.",
                    "description": "Keep the first execution active.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Second execution receives conflict.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]

    first_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )
    second_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )

    assert create_response.status_code == 201
    assert first_response.status_code == 202
    assert first_response.json()["status"] == "starting"
    assert second_response.status_code == 409
    assert first_response.json()["id"] in second_response.json()["detail"]


def test_orchestration_api_background_execution_cancel_starting(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Cancel detached orchestration from the API.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "Validate detached cancellation.",
                    "description": "Keep the execution queued.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Detached execution can be cancelled.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]
    start_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )
    execution_id = start_response.json()["id"]
    cancel_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions/{execution_id}/cancel"
    )
    get_response = client.get(f"/tasks/orchestrations/{run_id}/executions/{execution_id}")
    retry_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )

    assert create_response.status_code == 201
    assert start_response.status_code == 202
    assert start_response.json()["status"] == "starting"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert cancel_response.json()["completed_at"] is not None
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "cancelled"
    assert retry_response.status_code == 202
    assert retry_response.json()["id"] != execution_id


def test_orchestration_api_background_execution_cancel_completed_returns_409(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject terminal detached cancellation from the API.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "Validate terminal detached cancellation.",
                    "description": "Execution completes before cancellation.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Terminal cancellation returns conflict.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]
    start_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )
    execution_id = start_response.json()["id"]
    completed = _poll_api_execution(client, run_id, execution_id)
    cancel_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions/{execution_id}/cancel"
    )

    assert create_response.status_code == 201
    assert start_response.status_code == 202
    assert completed["status"] == "completed"
    assert cancel_response.status_code == 409


def test_orchestration_api_loop_rejects_active_background_execution(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject foreground loops during detached execution from the API.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "Validate detached loop exclusion.",
                    "description": "Keep the first execution active.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Foreground loop receives conflict.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]

    start_response = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        json={"max_iterations": 2},
    )
    loop_response = client.post(
        f"/tasks/orchestrations/{run_id}/loop",
        json={"max_iterations": 2},
    )

    assert create_response.status_code == 201
    assert start_response.status_code == 202
    assert loop_response.status_code == 409
    assert start_response.json()["id"] in loop_response.json()["detail"]


def test_orchestration_api_advance_and_cycle_reject_active_background_execution(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject foreground schedulers during detached execution from the API.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "Validate detached scheduler exclusion.",
                    "description": "Foreground schedulers should receive conflict.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Foreground advance and cycle receive conflict.",
                }
            ],
        },
    )
    run_id = create_response.json()["id"]

    start_response = client.post(f"/tasks/orchestrations/{run_id}/executions")
    advance_response = client.post(f"/tasks/orchestrations/{run_id}/advance")
    cycle_response = client.post(f"/tasks/orchestrations/{run_id}/cycle")

    assert create_response.status_code == 201
    assert start_response.status_code == 202
    assert advance_response.status_code == 409
    assert cycle_response.status_code == 409
    assert start_response.json()["id"] in advance_response.json()["detail"]
    assert start_response.json()["id"] in cycle_response.json()["detail"]


def test_orchestration_api_exposes_dependency_context_on_spawned_agent(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Coordinate TOKEN=objective-secret dependency context.",
            "tasks": [
                {
                    "id": "developer-implementation",
                    "title": "Implement SECRET=title-secret dependency context.",
                    "description": "Produce source changes.",
                    "role": "Developer",
                    "declared_write_paths": ["src/dgentic/orchestration.py"],
                    "validation": "Developer work complete.",
                },
                {
                    "id": "qa-validation",
                    "title": "Validate TOKEN=qa-title-secret dependency context.",
                    "description": "Validate source changes.",
                    "role": "QA",
                    "dependencies": ["developer-implementation"],
                    "declared_write_paths": ["tests/test_orchestration.py"],
                    "validation": "QA receives PASSWORD=validation-secret context.",
                },
            ],
        },
    )
    run_id = create_response.json()["id"]
    completed_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/developer-implementation",
        json={
            "status": "completed",
            "output": {
                "summary": "plain-secret-value",
                "credential": "SECRET=dependency-secret",
            },
        },
    )
    body = completed_response.json()
    qa_agent_id = body["tasks"][1]["agent_id"]
    agent_response = client.get(f"/agents/{qa_agent_id}")

    assert create_response.status_code == 201
    assert completed_response.status_code == 200
    assert body["scheduled_task_ids"] == ["qa-validation"]
    assert agent_response.status_code == 200
    agent = agent_response.json()
    serialized_context = "\n".join(agent["context"])
    serialized_agent = json.dumps(agent)
    assert agent["context"][0] == "Coordinate TOKEN=[REDACTED] dependency context."
    assert agent["task"] == "Validate TOKEN=[REDACTED] dependency context."
    assert agent["expected_output"] == "QA receives PASSWORD=[REDACTED] context."
    assert "Dependency developer-implementation (Developer) completed" in serialized_context
    assert "Implement SECRET=[REDACTED] dependency context" in serialized_context
    assert '"summary": "[REDACTED]"' in serialized_context
    assert '"credential": "[REDACTED]"' in serialized_context
    assert "qa-title-secret" not in serialized_agent
    assert "validation-secret" not in serialized_agent
    assert "objective-secret" not in serialized_context
    assert "title-secret" not in serialized_context
    assert "dependency-secret" not in serialized_context
    assert "plain-secret-value" not in serialized_context
    assert agent_response.json()["required_data"] == ["developer-implementation"]


def test_orchestration_api_exposes_shared_memory_context_on_spawned_agent(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    spoofed_memory_response = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "api-spoofed-shared-memory",
            "category": "orchestration_context",
            "description": "Spoofed memory must not enter context. PASSWORD=memory-secret",
            "tags": ["qa"],
            "relevance_score": 0.9,
            "owner_agent": "system",
        },
    )
    producer_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Produce QA validation memory.",
            "shared_memory_tags": ["qa"],
            "tasks": [
                {
                    "id": "qa-producer",
                    "title": "QA producer",
                    "description": "Publish memory context.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "QA publishes memory.",
                }
            ],
        },
    )
    producer_id = producer_response.json()["id"]
    completed_response = client.patch(
        f"/tasks/orchestrations/{producer_id}/tasks/qa-producer",
        json={
            "status": "completed",
            "output": {"summary": "Use API smoke coverage.", "password": "PASSWORD=memory-secret"},
        },
    )
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Coordinate QA validation with memory context.",
            "shared_memory_tags": ["qa"],
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Use memory context while validating.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "QA receives memory context.",
                }
            ],
        },
    )
    body = create_response.json()
    agent_id = body["tasks"][0]["agent_id"]
    agent_response = client.get(f"/agents/{agent_id}")
    list_response = client.get("/api/v1/memory/metadata?category=orchestration_context&tags=qa")

    assert spoofed_memory_response.status_code == 403
    assert producer_response.status_code == 201
    assert completed_response.status_code == 200
    assert create_response.status_code == 201
    assert agent_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    serialized_context = "\n".join(agent_response.json()["context"])
    assert f"Shared memory orchestration:{producer_id}:qa-producer" in serialized_context
    assert '"password": "[REDACTED]"' in serialized_context
    assert "api-spoofed-shared-memory" not in serialized_context
    assert "memory-secret" not in serialized_context


def test_orchestration_api_blocks_public_orchestration_metadata_writes(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_blocked = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "public-orchestration-context",
            "category": "orchestration_context",
            "description": "Caller-supplied orchestration memory.",
            "tags": ["qa-context"],
        },
    )
    planning_create = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "planning-memory",
            "category": "planning",
            "description": "Normal metadata remains caller writable.",
            "tags": ["qa-context"],
        },
    )
    promote_to_context = client.patch(
        f"/api/v1/memory/metadata/{planning_create.json()['id']}",
        json={"category": "orchestration_context"},
    )
    producer_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Publish service-authored shared memory.",
            "shared_memory_tags": ["qa-context"],
            "tasks": [
                {
                    "id": "qa-producer",
                    "title": "QA producer",
                    "description": "Publish memory context.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Shared memory is published by orchestration.",
                }
            ],
        },
    )
    producer_id = producer_response.json()["id"]
    completed_response = client.patch(
        f"/tasks/orchestrations/{producer_id}/tasks/qa-producer",
        json={"status": "completed", "output": {"summary": "Service-authored memory."}},
    )
    list_response = client.get(
        "/api/v1/memory/metadata?category=orchestration_context&tags=qa-context"
    )
    metadata_id = list_response.json()["items"][0]["id"]
    patch_context = client.patch(
        f"/api/v1/memory/metadata/{metadata_id}",
        json={"description": "Caller should not rewrite service-authored context."},
    )
    delete_context = client.delete(f"/api/v1/memory/metadata/{metadata_id}")

    assert create_blocked.status_code == 403
    assert planning_create.status_code == 201
    assert promote_to_context.status_code == 403
    assert producer_response.status_code == 201
    assert completed_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert patch_context.status_code == 403
    assert delete_context.status_code == 403


def test_orchestration_api_filters_runs_by_authenticated_task_owner(tmp_path, monkeypatch) -> None:
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Owner-scoped orchestration.",
        "tasks": [
            {
                "id": "qa-validation",
                "title": "QA validation",
                "description": "Validate owner filtering.",
                "role": "QA",
                "declared_write_paths": ["tests/test_orchestration.py"],
                "validation": "Owner filtering holds.",
            }
        ],
    }

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer alpha-token"},
        json=payload,
    )
    beta_list = client.get(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer beta-token"},
    )
    beta_get = client.get(
        f"/tasks/orchestrations/{alpha_create.json()['id']}",
        headers={"Authorization": "Bearer beta-token"},
    )
    admin_list = client.get(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert alpha_create.status_code == 201
    assert alpha_create.json()["requested_by"]
    assert beta_list.status_code == 200
    assert beta_list.json() == []
    assert beta_get.status_code == 404
    assert admin_list.status_code == 200
    assert [run["id"] for run in admin_list.json()] == [alpha_create.json()["id"]]
    get_settings.cache_clear()


def test_orchestration_api_operations_summary_respects_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Owner-scoped operations summary.",
        "tasks": [
            {
                "id": "qa-validation",
                "title": "QA validation",
                "description": "Validate operations summary.",
                "role": "QA",
                "declared_write_paths": ["tests/test_api.py"],
                "validation": "Owner summary holds.",
            }
        ],
    }
    alpha_headers = {"Authorization": "Bearer alpha-token"}
    beta_headers = {"Authorization": "Bearer beta-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}

    alpha_create = client.post("/tasks/orchestrations", headers=alpha_headers, json=payload)
    beta_create = client.post("/tasks/orchestrations", headers=beta_headers, json=payload)
    alpha_run_id = alpha_create.json()["id"]
    alpha_start = client.post(
        f"/tasks/orchestrations/{alpha_run_id}/executions",
        headers=alpha_headers,
        json={"max_iterations": 2},
    )
    alpha_summary = client.get(
        "/tasks/orchestrations/operations/summary",
        headers=alpha_headers,
    )
    beta_summary = client.get(
        "/tasks/orchestrations/operations/summary",
        headers=beta_headers,
    )
    admin_summary = client.get(
        "/tasks/orchestrations/operations/summary",
        headers=admin_headers,
    )

    assert alpha_create.status_code == 201
    assert beta_create.status_code == 201
    assert alpha_start.status_code == 202
    assert alpha_summary.status_code == 200
    assert beta_summary.status_code == 200
    assert admin_summary.status_code == 200
    assert alpha_summary.json()["total_runs"] == 1
    assert alpha_summary.json()["active_execution_count"] == 1
    assert alpha_summary.json()["active_execution_ids"] == [alpha_start.json()["id"]]
    assert beta_summary.json()["total_runs"] == 1
    assert beta_summary.json()["active_execution_count"] == 0
    assert beta_summary.json()["active_execution_ids"] == []
    assert admin_summary.json()["total_runs"] == 2
    assert admin_summary.json()["active_execution_count"] == 1
    get_settings.cache_clear()


def test_orchestration_api_shared_memory_respects_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    alpha_headers = {"Authorization": "Bearer alpha-token"}
    beta_headers = {"Authorization": "Bearer beta-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}
    producer_payload = {
        "objective": "Alpha produces owner-scoped shared memory.",
        "shared_memory_tags": ["qa-context"],
        "tasks": [
            {
                "id": "qa-producer",
                "title": "QA producer",
                "description": "Publish owner-scoped memory.",
                "role": "QA",
                "declared_write_paths": ["tests/test_api.py"],
                "validation": "Shared memory is published.",
            }
        ],
    }
    consumer_task = {
        "id": "qa-consumer",
        "title": "QA consumer",
        "description": "Consume owner-scoped memory.",
        "role": "QA",
        "declared_write_paths": ["tests/test_api.py"],
        "validation": "Shared memory is owner-scoped.",
    }

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers=alpha_headers,
        json=producer_payload,
    )
    alpha_run_id = alpha_create.json()["id"]
    alpha_complete = client.patch(
        f"/tasks/orchestrations/{alpha_run_id}/tasks/qa-producer",
        headers=alpha_headers,
        json={"status": "completed", "output": {"summary": "Alpha-only memory."}},
    )
    beta_create = client.post(
        "/tasks/orchestrations",
        headers=beta_headers,
        json={
            "objective": "Beta tries matching shared memory tag.",
            "shared_memory_tags": ["qa-context"],
            "tasks": [consumer_task],
        },
    )
    alpha_consumer = client.post(
        "/tasks/orchestrations",
        headers=alpha_headers,
        json={
            "objective": "Alpha consumes matching shared memory tag.",
            "shared_memory_tags": ["qa-context"],
            "tasks": [consumer_task],
        },
    )
    beta_agent_response = client.get(
        f"/agents/{beta_create.json()['tasks'][0]['agent_id']}",
        headers=admin_headers,
    )
    alpha_agent_response = client.get(
        f"/agents/{alpha_consumer.json()['tasks'][0]['agent_id']}",
        headers=admin_headers,
    )

    assert alpha_create.status_code == 201
    assert alpha_complete.status_code == 200
    assert beta_create.status_code == 201
    assert alpha_consumer.status_code == 201
    assert beta_agent_response.status_code == 200
    assert alpha_agent_response.status_code == 200
    beta_context = "\n".join(beta_agent_response.json()["context"])
    alpha_context = "\n".join(alpha_agent_response.json()["context"])
    assert f"orchestration:{alpha_run_id}:qa-producer" not in beta_context
    assert f"orchestration:{alpha_run_id}:qa-producer" in alpha_context
    get_settings.cache_clear()


def test_orchestration_api_agent_reads_respect_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_shared_memory_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    alpha_headers = {"Authorization": "Bearer alpha-token"}
    beta_headers = {"Authorization": "Bearer beta-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers=alpha_headers,
        json={
            "objective": "Alpha private agent context.",
            "tasks": [
                {
                    "id": "qa-alpha",
                    "title": "QA alpha",
                    "description": "Keep alpha context owner scoped.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Alpha agent is visible to alpha and admin.",
                }
            ],
        },
    )
    alpha_agent_id = alpha_create.json()["tasks"][0]["agent_id"]
    alpha_get = client.get(f"/agents/{alpha_agent_id}", headers=alpha_headers)
    beta_get = client.get(f"/agents/{alpha_agent_id}", headers=beta_headers)
    beta_list = client.get("/agents", headers=beta_headers)
    admin_get = client.get(f"/agents/{alpha_agent_id}", headers=admin_headers)

    assert alpha_create.status_code == 201
    assert alpha_get.status_code == 200
    assert beta_get.status_code == 404
    assert beta_list.status_code == 200
    assert alpha_agent_id not in {agent["id"] for agent in beta_list.json()}
    assert admin_get.status_code == 200
    get_settings.cache_clear()
    reset_database_state()


def test_orchestration_api_shared_memory_metadata_reads_are_owner_scoped(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_shared_memory_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    alpha_headers = {"Authorization": "Bearer alpha-token"}
    beta_headers = {"Authorization": "Bearer beta-token"}
    admin_headers = {"Authorization": "Bearer admin-token"}

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers=alpha_headers,
        json={
            "objective": "Alpha produces private shared memory.",
            "shared_memory_tags": ["qa-context"],
            "tasks": [
                {
                    "id": "qa-producer",
                    "title": "QA producer",
                    "description": "Publish alpha memory.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Shared memory is owner scoped.",
                }
            ],
        },
    )
    alpha_run_id = alpha_create.json()["id"]
    alpha_complete = client.patch(
        f"/tasks/orchestrations/{alpha_run_id}/tasks/qa-producer",
        headers=alpha_headers,
        json={"status": "completed", "output": {"summary": "Alpha private memory."}},
    )
    alpha_list = client.get(
        "/api/v1/memory/metadata?category=orchestration_context&tags=qa-context",
        headers=alpha_headers,
    )
    metadata_id = alpha_list.json()["items"][0]["id"]
    beta_list = client.get(
        "/api/v1/memory/metadata?category=orchestration_context&tags=qa-context",
        headers=beta_headers,
    )
    beta_get = client.get(f"/api/v1/memory/metadata/{metadata_id}", headers=beta_headers)
    beta_retrieve = client.get(
        "/api/v1/memory/retrieve/metadata?category=orchestration_context",
        headers=beta_headers,
    )
    admin_get = client.get(f"/api/v1/memory/metadata/{metadata_id}", headers=admin_headers)

    assert alpha_create.status_code == 201
    assert alpha_complete.status_code == 200
    assert alpha_list.status_code == 200
    assert alpha_list.json()["total"] == 1
    assert beta_list.status_code == 200
    assert beta_list.json()["total"] == 0
    assert beta_get.status_code == 404
    assert beta_retrieve.status_code == 200
    assert beta_retrieve.json()["total"] == 0
    assert admin_get.status_code == 200
    assert admin_get.json()["entity_id"] == f"orchestration:{alpha_run_id}:qa-producer"
    get_settings.cache_clear()
    reset_database_state()


def test_orchestration_api_shared_memory_run_policy_blocks_cross_run_context(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    producer_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Produce run-scoped API memory.",
            "shared_memory_tags": ["qa-context"],
            "shared_memory_policy": "run",
            "tasks": [
                {
                    "id": "qa-producer",
                    "title": "QA producer",
                    "description": "Publish run-scoped memory.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Memory is run scoped.",
                }
            ],
        },
    )
    producer_id = producer_response.json()["id"]
    completed_response = client.patch(
        f"/tasks/orchestrations/{producer_id}/tasks/qa-producer",
        json={"status": "completed", "output": {"summary": "Run-scoped API memory."}},
    )
    consumer_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Try cross-run memory reuse.",
            "shared_memory_tags": ["qa-context"],
            "tasks": [
                {
                    "id": "qa-consumer",
                    "title": "QA consumer",
                    "description": "Try run-scoped memory.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Memory is not imported.",
                }
            ],
        },
    )
    agent_response = client.get(f"/agents/{consumer_response.json()['tasks'][0]['agent_id']}")
    context = "\n".join(agent_response.json()["context"])

    assert producer_response.status_code == 201
    assert completed_response.status_code == 200
    assert consumer_response.status_code == 201
    assert agent_response.status_code == 200
    assert producer_response.json()["shared_memory_policy"] == "run"
    assert consumer_response.json()["shared_memory_policy"] == "owner"
    assert f"orchestration:{producer_id}:qa-producer" not in context
    assert "Run-scoped API memory" not in context


def test_orchestration_api_shared_memory_consumer_run_policy_blocks_owner_context(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    producer_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Produce owner-scoped API memory.",
            "shared_memory_tags": ["qa-context"],
            "tasks": [
                {
                    "id": "qa-producer",
                    "title": "QA producer",
                    "description": "Publish owner-scoped memory.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Memory uses the default owner policy.",
                }
            ],
        },
    )
    producer_id = producer_response.json()["id"]
    completed_response = client.patch(
        f"/tasks/orchestrations/{producer_id}/tasks/qa-producer",
        json={"status": "completed", "output": {"summary": "Owner-scoped API memory."}},
    )
    consumer_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Run-scoped consumer should not import owner memory.",
            "shared_memory_tags": ["qa-context"],
            "shared_memory_policy": "run",
            "tasks": [
                {
                    "id": "qa-consumer",
                    "title": "QA consumer",
                    "description": "Reject cross-run owner memory.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Memory is not imported.",
                }
            ],
        },
    )
    agent_response = client.get(f"/agents/{consumer_response.json()['tasks'][0]['agent_id']}")
    context = "\n".join(agent_response.json()["context"])

    assert producer_response.status_code == 201
    assert completed_response.status_code == 200
    assert consumer_response.status_code == 201
    assert agent_response.status_code == 200
    assert producer_response.json()["shared_memory_policy"] == "owner"
    assert consumer_response.json()["shared_memory_policy"] == "run"
    assert f"orchestration:{producer_id}:qa-producer" not in context
    assert "Owner-scoped API memory" not in context


def test_orchestration_api_shared_memory_policy_rejects_invalid_value(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Reject invalid shared memory policy.",
            "shared_memory_tags": ["qa-context"],
            "shared_memory_policy": "workspace",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate shared memory policy contract.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Invalid policy is rejected.",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "shared_memory_policy"]


def test_orchestration_api_background_execution_respects_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Owner-scoped detached orchestration.",
        "tasks": [
            {
                "id": "qa-validation",
                "title": "QA validation",
                "description": "Validate detached owner filtering.",
                "role": "QA",
                "declared_write_paths": ["tests/test_api.py"],
                "validation": "Owner filtering holds.",
            }
        ],
    }

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer alpha-token"},
        json=payload,
    )
    run_id = alpha_create.json()["id"]
    alpha_start = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        headers={"Authorization": "Bearer alpha-token"},
        json={"max_iterations": 2},
    )
    execution_id = alpha_start.json()["id"]
    completed = _poll_api_execution(
        client,
        run_id,
        execution_id,
        headers={"Authorization": "Bearer alpha-token"},
    )
    beta_list = client.get(
        f"/tasks/orchestrations/{run_id}/executions",
        headers={"Authorization": "Bearer beta-token"},
    )
    beta_get = client.get(
        f"/tasks/orchestrations/{run_id}/executions/{execution_id}",
        headers={"Authorization": "Bearer beta-token"},
    )
    admin_list = client.get(
        f"/tasks/orchestrations/{run_id}/executions",
        headers={"Authorization": "Bearer admin-token"},
    )
    admin_get = client.get(
        f"/tasks/orchestrations/{run_id}/executions/{execution_id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert alpha_create.status_code == 201
    assert alpha_start.status_code == 202
    assert alpha_start.json()["requested_by"] == alpha_create.json()["requested_by"]
    assert completed["status"] == "completed"
    assert beta_list.status_code == 404
    assert beta_get.status_code == 404
    assert admin_list.status_code == 200
    assert [execution["id"] for execution in admin_list.json()] == [execution_id]
    assert admin_get.status_code == 200
    assert admin_get.json()["id"] == execution_id
    get_settings.cache_clear()


def test_orchestration_api_background_execution_cancel_respects_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    class HoldingThread:
        def __init__(self, target, args, daemon):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            return None

    monkeypatch.setattr("dgentic.orchestration.Thread", HoldingThread)
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Owner-scoped detached cancellation.",
        "tasks": [
            {
                "id": "qa-validation",
                "title": "QA validation",
                "description": "Validate detached cancel owner filtering.",
                "role": "QA",
                "declared_write_paths": ["tests/test_api.py"],
                "validation": "Owner filtering holds.",
            }
        ],
    }

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer alpha-token"},
        json=payload,
    )
    run_id = alpha_create.json()["id"]
    alpha_start = client.post(
        f"/tasks/orchestrations/{run_id}/executions",
        headers={"Authorization": "Bearer alpha-token"},
        json={"max_iterations": 2},
    )
    execution_id = alpha_start.json()["id"]
    beta_cancel = client.post(
        f"/tasks/orchestrations/{run_id}/executions/{execution_id}/cancel",
        headers={"Authorization": "Bearer beta-token"},
    )
    admin_cancel = client.post(
        f"/tasks/orchestrations/{run_id}/executions/{execution_id}/cancel",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert alpha_create.status_code == 201
    assert alpha_start.status_code == 202
    assert beta_cancel.status_code == 404
    assert admin_cancel.status_code == 200
    assert admin_cancel.json()["status"] == "cancelled"
    get_settings.cache_clear()


def test_orchestration_api_recovery_respects_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Owner-scoped recovery.",
        "tasks": [
            {
                "id": "qa-source-edit",
                "title": "QA source edit",
                "description": "Blocked source edit.",
                "role": "QA",
                "declared_write_paths": ["src/dgentic/orchestration.py"],
                "validation": "Owner filtering holds.",
            }
        ],
    }

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer alpha-token"},
        json=payload,
    )
    run_id = alpha_create.json()["id"]
    beta_recover = client.post(
        f"/tasks/orchestrations/{run_id}/tasks/qa-source-edit/recover",
        headers={"Authorization": "Bearer beta-token"},
        json={
            "resolution": "Try to recover another owner run.",
            "role": "Developer",
            "declared_write_paths": ["src/dgentic/orchestration.py"],
        },
    )
    admin_recover = client.post(
        f"/tasks/orchestrations/{run_id}/tasks/qa-source-edit/recover",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "resolution": "Admin corrected ownership.",
            "role": "Developer",
            "declared_write_paths": ["src/dgentic/orchestration.py"],
        },
    )

    assert alpha_create.status_code == 201
    assert beta_recover.status_code == 404
    assert admin_recover.status_code == 200
    assert admin_recover.json()["tasks"][0]["status"] == "running"
    get_settings.cache_clear()


def test_orchestration_api_resolves_manual_blocker_with_admin_audit(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Resolve manual blocker through admin review.",
        "required_dod_evidence": ["tests"],
        "tasks": [
            {
                "id": "qa-validation",
                "title": "QA validation",
                "description": "Validate manual blocker resolution.",
                "role": "QA",
                "declared_write_paths": ["tests/test_orchestration.py"],
                "validation": "Manual blocker can be resolved.",
            }
        ],
    }

    create_response = client.post(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer alpha-token"},
        json=payload,
    )
    run_id = create_response.json()["id"]
    blocked_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/qa-validation",
        headers={"Authorization": "Bearer alpha-token"},
        json={"status": "blocked", "error": "Needs security review."},
    )
    blocker_id = blocked_response.json()["blockers"][0]["id"]
    task_token_response = client.post(
        f"/tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve",
        headers={"Authorization": "Bearer beta-token"},
        json={"resolution": "Attempt non-admin resolution.", "reschedule": True},
    )
    admin_response = client.post(
        f"/tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve",
        headers={"Authorization": "Bearer admin-token"},
        json={"resolution": "SECRET=hidden accepted mitigation.", "reschedule": True},
    )
    completed_response = client.patch(
        f"/tasks/orchestrations/{run_id}/tasks/qa-validation",
        headers={"Authorization": "Bearer alpha-token"},
        json={"status": "completed", "output": {"tests": "passed"}},
    )
    close_response = client.post(
        f"/tasks/orchestrations/{run_id}/close",
        headers={"Authorization": "Bearer alpha-token"},
        json={"evidence": {"tests": "pytest passed"}},
    )
    logs_response = client.get(
        "/logs",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert create_response.status_code == 201
    assert blocked_response.status_code == 200
    assert task_token_response.status_code == 403
    assert admin_response.status_code == 200
    body = admin_response.json()
    assert body["tasks"][0]["status"] == "running"
    assert body["follow_ups"] == []
    assert body["scheduled_task_ids"] == ["qa-validation"]
    assert body["blockers"][0]["status"] == "resolved"
    assert body["blockers"][0]["resolution"] == "SECRET=[REDACTED] accepted mitigation."
    assert body["blockers"][0]["resolved_by"]
    assert completed_response.status_code == 200
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "completed"
    assert close_response.json()["blockers"][0]["status"] == "resolved"
    resolution_event = next(
        event
        for event in logs_response.json()
        if event["subject_id"] == run_id and event["message"] == "Resolved orchestration blocker."
    )
    assert resolution_event["metadata"]["resolution"] == "SECRET=[REDACTED] accepted mitigation."
    assert "hidden" not in json.dumps(resolution_event)
    get_settings.cache_clear()


def test_orchestration_api_cycle_respects_authenticated_task_owner(
    tmp_path,
    monkeypatch,
) -> None:
    _configure_production_task_api_state(tmp_path, monkeypatch)
    client = TestClient(create_app())
    payload = {
        "objective": "Owner-scoped cycle.",
        "tasks": [
            {
                "id": "qa-validation",
                "title": "QA validation",
                "description": "Validate owner filtering.",
                "role": "QA",
                "declared_write_paths": ["tests/test_orchestration.py"],
                "validation": "Owner filtering holds.",
            }
        ],
    }

    alpha_create = client.post(
        "/tasks/orchestrations",
        headers={"Authorization": "Bearer alpha-token"},
        json=payload,
    )
    run_id = alpha_create.json()["id"]
    beta_cycle = client.post(
        f"/tasks/orchestrations/{run_id}/cycle",
        headers={"Authorization": "Bearer beta-token"},
    )
    admin_cycle = client.post(
        f"/tasks/orchestrations/{run_id}/cycle",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert alpha_create.status_code == 201
    assert beta_cycle.status_code == 404
    assert admin_cycle.status_code == 200
    assert admin_cycle.json()["id"] == run_id
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


def test_guardrails_network_returns_policy_decision(monkeypatch) -> None:
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": "deny",
                        "reason": "Blocked by QA policy.",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/guardrails/network",
        json={"url": "https://blocked.example.test/v1/chat/completions"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "allowed": False,
        "url": "https://blocked.example.test/v1/chat/completions",
        "host": "blocked.example.test",
        "mode": "deny",
        "matched_domain": "blocked.example.test",
        "reason": "Blocked by QA policy.",
    }
    get_settings.cache_clear()


def test_network_approval_api_lifecycle_redacts_safe_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "provider.example.test",
                        "mode": "approval_required",
                        "reason": "Review provider token=policy-secret.",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/network/approvals",
        json={
            "url": "https://provider.example.test/v1?token=url-secret",
            "surface": "provider",
            "action": "generate",
            "requested_by": "operator SECRET=requester-secret",
        },
    )

    assert create_response.status_code == 201
    body = create_response.json()
    approval_id = body["id"]
    assert body["url"] == "https://provider.example.test/v1"
    assert body["requested_by"] == "operator SECRET=[REDACTED]"
    assert body["policy_reason"] == "Review provider token=[REDACTED]"
    assert body["status"] == "pending"

    list_response = client.get("/network/approvals?status=pending")
    review_response = client.get(f"/network/approvals/{approval_id}/review")
    approve_response = client.post(
        f"/network/approvals/{approval_id}/approve",
        json={
            "decided_by": "reviewer TOKEN=reviewer-secret",
            "reason": "Approved PASSWORD=reason-secret",
        },
    )

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == approval_id
    assert review_response.status_code == 200
    assert review_response.json()["direct_execute_available"] is False
    assert approve_response.status_code == 200
    assert approve_response.json()["decided_by"] == "reviewer TOKEN=[REDACTED]"

    response_text = json.dumps(
        {
            "create": create_response.json(),
            "list": list_response.json(),
            "review": review_response.json(),
            "approve": approve_response.json(),
        }
    )
    stored = (tmp_path / "state" / "network-approvals.json").read_text(encoding="utf-8")
    for secret in [
        "url-secret",
        "policy-secret",
        "requester-secret",
        "reviewer-secret",
        "reason-secret",
    ]:
        assert secret not in response_text
        assert secret not in stored
    get_settings.cache_clear()


def test_network_approval_api_blocks_partial_active_orchestration_context(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "provider.example.test",
                        "mode": "approval_required",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    client = TestClient(create_app())
    create_run_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Block partial network approval context.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate network approval context binding.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Network approval context is verified.",
                }
            ],
        },
    )
    task = create_run_response.json()["tasks"][0]

    response = client.post(
        "/network/approvals",
        json={
            "url": "https://provider.example.test/v1",
            "surface": "provider",
            "action": "generate",
            "requested_by": "operator",
            "agent_id": task["agent_id"],
        },
    )

    assert create_run_response.status_code == 201
    assert response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in response.json()["detail"]
    get_settings.cache_clear()


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


def test_api_filesystem_write_serializes_orchestration_decisions(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Bind filesystem writes to the scheduled QA task.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Write only declared QA test artifacts.",
                    "role": "QA",
                    "declared_write_paths": ["tests/generated-api-write.txt"],
                    "validation": "Filesystem binding is enforced.",
                }
            ],
        },
    )
    task = create_response.json()["tasks"][0]
    context = {
        "agent_id": task["agent_id"],
        "agent_role": task["role"],
        "task_id": task["id"],
    }

    write_response = client.post(
        "/filesystem/write",
        json={
            **context,
            "path": "tests/generated-api-write.txt",
            "content": "orchestration-bound write",
        },
    )
    blocked_response = client.post(
        "/filesystem/write",
        json={
            **context,
            "path": "README.md",
            "content": "outside declared write paths",
        },
    )
    logs_response = client.get("/logs?event_type=filesystem")

    assert create_response.status_code == 201
    assert write_response.status_code == 200
    assert write_response.json()["bytes_written"] == len("orchestration-bound write")
    assert blocked_response.status_code == 403
    assert (
        "outside the orchestration task declared write paths" in blocked_response.json()["detail"]
    )
    assert logs_response.status_code == 200

    policy_events = [
        event
        for event in logs_response.json()
        if event["message"] == "Evaluated filesystem access policy."
    ]
    allowed_event = next(
        event
        for event in policy_events
        if event["metadata"]["path"].replace("\\", "/") == "tests/generated-api-write.txt"
    )
    blocked_event = next(
        event for event in policy_events if event["metadata"]["path"] == "README.md"
    )

    assert allowed_event["metadata"]["orchestration"] == {
        "allowed": True,
        "reason": "Filesystem write action is within the orchestration task declared write paths.",
        "run_id": create_response.json()["id"],
        "task_id": "qa-validation",
        "agent_id": task["agent_id"],
        "agent_role": "QA",
        "violating_paths": [],
    }
    assert blocked_event["metadata"]["orchestration"]["allowed"] is False
    assert blocked_event["metadata"]["orchestration"]["violating_paths"] == ["README.md"]
    get_settings.cache_clear()


def test_api_command_policy_serializes_orchestration_decisions(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Bind command policy checks to the scheduled QA task.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Evaluate orchestration-bound command policy.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Command policy binding is enforced.",
                }
            ],
        },
    )
    task = create_response.json()["tasks"][0]

    response = client.post(
        "/guardrails/commands",
        json={
            "command": "cmd /c echo api-bound",
            "agent_id": task["agent_id"],
            "agent_role": task["role"],
            "task_id": task["id"],
        },
    )

    assert create_response.status_code == 201
    assert response.status_code == 200
    assert response.json()["permission_mode"] == "autopilot_safe"
    assert response.json()["orchestration"] == {
        "allowed": True,
        "reason": "CLI action is bound to a running orchestration task.",
        "run_id": create_response.json()["id"],
        "task_id": "qa-validation",
        "agent_id": task["agent_id"],
        "agent_role": "QA",
        "violating_paths": [],
    }
    get_settings.cache_clear()


def test_api_cli_runtime_blocks_partial_active_orchestration_context(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Block partial CLI runtime context for active QA task.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate API runtime orchestration binding.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "CLI runtime binding is enforced.",
                }
            ],
        },
    )
    task = create_response.json()["tasks"][0]

    execute_response = client.post(
        "/cli/execute",
        json={
            "command": "cmd /c echo should-not-run",
            "agent_id": task["agent_id"],
        },
    )
    run_response = client.post(
        "/cli/runs",
        json={
            "command": "cmd /c echo should-not-start",
            "task_id": task["id"],
        },
    )
    approval_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={
            "command": "python --version",
            "agent_id": task["agent_id"],
        },
    )

    assert create_response.status_code == 201
    assert execute_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in execute_response.json()["detail"]
    assert run_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in run_response.json()["detail"]
    assert approval_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in approval_response.json()["detail"]
    get_settings.cache_clear()


def test_api_execute_approved_cli_command_rechecks_active_orchestration_context(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    approval_response = client.post(
        "/cli/approvals?requested_by=tester",
        json={
            "command": "python --version",
            "task_id": "qa-validation",
        },
    )
    approval_id = approval_response.json()["id"]
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Recheck orchestration context before direct approval execution.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate approved command orchestration binding.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Direct approval execution is rechecked.",
                }
            ],
        },
    )
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
    )
    execute_response = client.post(f"/cli/approvals/{approval_id}/execute")

    assert approval_response.status_code == 201
    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert execute_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in execute_response.json()["detail"]
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


def test_filesystem_api_uses_authenticated_principal_as_audit_actor(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    token = "filesystem-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=filesystem,logs")
    get_settings.cache_clear()
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    write_response = client.post(
        "/filesystem/write",
        headers=headers,
        json={"path": "notes/audit.txt", "content": "principal audit", "create_parent_dirs": True},
    )
    read_response = client.post(
        "/filesystem/read",
        headers=headers,
        json={"path": "notes/audit.txt"},
    )
    logs_response = client.get("/logs?event_type=filesystem", headers=headers)

    assert write_response.status_code == 200
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "principal audit"
    assert any(
        event["message"] == "Evaluated filesystem access policy." and event["actor"] == actor_id
        for event in logs_response.json()
    )
    assert any(
        event["message"] == "Wrote guarded text file." and event["actor"] == actor_id
        for event in logs_response.json()
    )
    assert any(
        event["message"] == "Read guarded text file." and event["actor"] == actor_id
        for event in logs_response.json()
    )
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


def test_provider_routing_prefers_local_when_privacy_is_required(monkeypatch) -> None:
    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    providers_response = client.get("/providers")
    route_response = client.post("/routing/decide", json={"privacy_required": True})
    external_route_response = client.post(
        "/routing/decide",
        json={"privacy_required": False, "required_capabilities": ["external"]},
    )

    assert providers_response.status_code == 200
    assert len(providers_response.json()) >= 2
    assert {provider["id"] for provider in providers_response.json()} >= {"ollama", "lm-studio"}
    external_provider = next(
        provider
        for provider in providers_response.json()
        if provider["id"] == "external-placeholder"
    )
    assert external_provider["enabled"] is False
    assert external_provider["model_names"] == []
    assert external_provider["supports_streaming"] is False
    ollama_provider = next(
        provider for provider in providers_response.json() if provider["id"] == "ollama"
    )
    assert ollama_provider["supports_streaming"] is True
    assert "streaming" in ollama_provider["capabilities"]
    lm_studio_provider = next(
        provider for provider in providers_response.json() if provider["id"] == "lm-studio"
    )
    assert lm_studio_provider["supports_streaming"] is True
    assert "streaming" in lm_studio_provider["capabilities"]
    assert route_response.status_code == 200
    assert route_response.json()["provider_id"] in {"ollama", "lm-studio"}
    assert route_response.json()["candidate_scores"]
    assert external_route_response.status_code == 404
    assert "No provider satisfies" in external_route_response.text


def test_provider_listing_and_health_do_not_leak_invalid_configured_base_url(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_OLLAMA_BASE_URL",
        "http://operator:provider-password-secret@127.0.0.1:11434",
    )
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        return {"models": [{"name": "llama3.1"}]}

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    providers_response = client.get("/providers")
    health_response = client.get("/providers/ollama/health")
    logs_response = client.get("/logs?event_type=provider")

    assert providers_response.status_code == 200
    assert health_response.status_code == 200
    assert calls == ["http://127.0.0.1:1234/v1/models"]
    ollama_config = next(
        provider for provider in providers_response.json() if provider["id"] == "ollama"
    )
    assert ollama_config["base_url"] is None
    assert health_response.json()["available"] is False
    serialized = providers_response.text + health_response.text + logs_response.text
    assert "provider-password-secret" not in serialized
    get_settings.cache_clear()


def configure_external_provider_api(
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


def openai_stream_lines(*chunks: dict, done: bool = True) -> list[str]:
    lines = [f"data: {json.dumps(chunk)}\n" for chunk in chunks]
    if done:
        lines.append("data: [DONE]\n")
    return lines


def test_external_provider_listing_disabled_without_configuration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "")
    monkeypatch.delenv("DGENTIC_TEST_EXTERNAL_API_KEY", raising=False)
    get_settings.cache_clear()
    transport_calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        transport_calls.append(request.full_url)
        raise AssertionError("external transport should not be called")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    providers_response = client.get("/providers")
    health_response = client.get(
        f"/providers/{provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}/health"
    )
    route_response = client.post(
        "/routing/decide",
        json={"privacy_required": False, "required_capabilities": ["external"]},
    )
    logs_response = client.get("/logs?event_type=provider")

    assert providers_response.status_code == 200
    external_provider = next(
        provider
        for provider in providers_response.json()
        if provider["id"] == provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    )
    assert external_provider["enabled"] is False
    assert external_provider["model_names"] == []
    assert external_provider["base_url"] is None
    assert health_response.status_code == 200
    assert health_response.json()["available"] is False
    assert route_response.status_code == 404
    assert transport_calls == []
    serialized = providers_response.text + health_response.text + logs_response.text
    assert "external-api-key-secret" not in serialized
    get_settings.cache_clear()


def test_routing_selects_configured_external_when_requested(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={"privacy_required": False, "required_capabilities": ["external"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider_id"] == provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    assert body["model_name"] == "gpt-test"
    assert body["candidate_scores"][provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID] > 0
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_routing_rejects_provider_above_max_cost(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={
            "privacy_required": False,
            "required_capabilities": ["external"],
            "max_cost_usd": 0.0,
        },
    )

    assert response.status_code == 404
    assert "No provider satisfies" in response.text
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_routing_uses_configured_external_model_request_price(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": 0.5,
                        "completion_usd_per_1k_tokens": 1.0,
                        "request_estimate_usd": 0.03,
                    }
                }
            }
        ),
    )
    configure_external_provider_api(monkeypatch, models="gpt-test")

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={
            "privacy_required": False,
            "required_capabilities": ["external"],
            "max_cost_usd": 0.02,
        },
    )

    assert response.status_code == 404
    assert "No provider satisfies" in response.text
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_routing_selects_configured_role_provider_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_ROLE_ROUTING",
        json.dumps({"reviewer": {"provider_id": "lm-studio", "model": "local-model"}}),
    )
    get_settings.cache_clear()

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post("/routing/decide", json={"role": "reviewer"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider_id"] == "lm-studio"
    assert body["model_name"] == "local-model"
    assert body["reason"] == "Routing selected the configured provider for the requested role."
    assert body["candidate_scores"]["lm-studio"] > 0
    get_settings.cache_clear()


def test_routing_role_preference_respects_privacy_without_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_ROLE_ROUTING",
        json.dumps(
            {
                "reviewer": {
                    "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                    "model": "gpt-test",
                }
            }
        ),
    )
    configure_external_provider_api(monkeypatch)

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={"role": "reviewer", "privacy_required": True},
    )

    assert response.status_code == 404
    assert "configured role routing policy" in response.text
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_routing_role_preference_respects_max_cost_without_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_ROLE_ROUTING",
        json.dumps(
            {
                "reviewer": {
                    "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                    "model": "gpt-test",
                }
            }
        ),
    )
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": 0.5,
                        "completion_usd_per_1k_tokens": 1.0,
                        "request_estimate_usd": 0.03,
                    }
                }
            }
        ),
    )
    configure_external_provider_api(monkeypatch)

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={"role": "reviewer", "max_cost_usd": 0.02},
    )

    assert response.status_code == 404
    assert "configured role routing policy" in response.text
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_routing_role_preference_uses_configured_model_cost(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_ROLE_ROUTING",
        json.dumps(
            {
                "reviewer": {
                    "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
                    "model": "expensive-model",
                }
            }
        ),
    )
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "cheap-model": {"request_estimate_usd": 0.01},
                    "expensive-model": {"request_estimate_usd": 0.05},
                }
            }
        ),
    )
    configure_external_provider_api(monkeypatch, models="cheap-model,expensive-model")

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={"role": "reviewer", "max_cost_usd": 0.02},
    )

    assert response.status_code == 404
    assert "configured role routing policy" in response.text
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_routing_rejects_invalid_role_routing_before_probes(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_ROLE_ROUTING", "not-json")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        raise AssertionError("provider probes should not run for invalid role routing")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post("/routing/decide", json={"role": "reviewer"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Provider role routing is invalid."
    assert calls == []
    assert "not-json" not in response.text
    get_settings.cache_clear()


def test_routing_rejects_unknown_role_provider_before_probes(monkeypatch) -> None:
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_ROLE_ROUTING",
        json.dumps({"reviewer": {"provider_id": "unknown", "model": "gpt-test"}}),
    )
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        raise AssertionError("provider probes should not run for invalid role provider")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post("/routing/decide", json={"role": "reviewer"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Provider role routing is invalid."
    assert calls == []
    get_settings.cache_clear()


def test_routing_rejects_unavailable_role_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_ROLE_ROUTING",
        json.dumps({"reviewer": {"provider_id": "lm-studio", "model": "missing-model"}}),
    )
    get_settings.cache_clear()

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post("/routing/decide", json={"role": "reviewer"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Configured role routing model is not available."
    get_settings.cache_clear()


def test_routing_rejects_invalid_pricing_catalog_before_probes(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_PRICING_CATALOG", "not-json")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        raise AssertionError("provider probes should not run for invalid pricing")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={"privacy_required": False, "required_capabilities": ["external"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Provider pricing catalog is invalid."
    assert calls == []
    get_settings.cache_clear()


@pytest.mark.parametrize("path", ["/providers", "/providers/ollama/health"])
def test_provider_listing_and_health_reject_invalid_pricing_before_probes(
    path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "")
    monkeypatch.setenv("DGENTIC_PROVIDER_PRICING_CATALOG", "not-json")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        raise AssertionError("provider probes should not run for invalid pricing")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.get(path)

    assert response.status_code == 503
    assert response.json()["detail"] == "Provider pricing catalog is invalid."
    assert calls == []
    assert "not-json" not in response.text
    get_settings.cache_clear()


@pytest.mark.parametrize("max_cost_usd", ["NaN", "Infinity", -0.01])
def test_routing_rejects_invalid_max_cost_before_scoring(
    max_cost_usd,
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        calls.append(url)
        raise AssertionError("provider probes should not run for invalid routing policy")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post(
        "/routing/decide",
        json={
            "privacy_required": False,
            "required_capabilities": ["external"],
            "max_cost_usd": max_cost_usd,
        },
    )

    assert response.status_code == 422
    assert calls == []


def test_routing_prefers_local_when_privacy_required_with_external_configured(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.post("/routing/decide", json={"privacy_required": True})

    assert response.status_code == 200
    assert response.json()["provider_id"] in {"ollama", "lm-studio"}
    assert (
        response.json()["candidate_scores"][provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID]
        == 0.0
    )
    assert "Privacy requirement" in response.json()["reason"]
    get_settings.cache_clear()


def test_configured_external_provider_health_is_config_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("external health should not call transport")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.get(
        f"/providers/{provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}/health"
    )

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["model_names"] == ["gpt-test", "gpt-other"]
    assert calls == []
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_configured_external_provider_with_credential_reference_does_not_resolve_secret(
    tmp_path,
    monkeypatch,
) -> None:
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
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_CREDENTIAL_REF", credential_ref.id)
    monkeypatch.delenv("DGENTIC_REF_EXTERNAL_API_KEY", raising=False)
    get_settings.cache_clear()

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        raise AssertionError("provider listing, health, and routing should not resolve secrets")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    providers_response = client.get("/providers")
    health_response = client.get(
        f"/providers/{provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}/health"
    )
    route_response = client.post(
        "/routing/decide",
        json={"privacy_required": False, "required_capabilities": ["external"]},
    )

    assert providers_response.status_code == 200
    external_provider = next(
        provider
        for provider in providers_response.json()
        if provider["id"] == provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    )
    assert external_provider["enabled"] is True
    assert health_response.status_code == 200
    assert health_response.json()["available"] is True
    assert route_response.status_code == 200
    assert route_response.json()["provider_id"] == (
        provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    )
    get_settings.cache_clear()


def test_configured_external_provider_lists_streaming_support(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    client = TestClient(create_app())

    response = client.get("/providers")

    assert response.status_code == 200
    external_provider = next(
        provider
        for provider in response.json()
        if provider["id"] == provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    )
    assert external_provider["enabled"] is True
    assert external_provider["supports_streaming"] is True
    assert "streaming" in external_provider["capabilities"]
    get_settings.cache_clear()


def test_plain_http_external_provider_configuration_stays_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch, base_url="http://provider.example.test/v1")
    calls: list[str] = []

    def fake_get_json(url: str) -> dict:
        if url.endswith("/api/tags"):
            return {"models": [{"name": "llama3.1"}]}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "local-model"}]}
        raise AssertionError(f"Unexpected provider health URL: {url}")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("external health should not call transport")

    monkeypatch.setattr(providers, "_get_json", fake_get_json)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    providers_response = client.get("/providers")
    health_response = client.get(
        f"/providers/{provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}/health"
    )
    route_response = client.post(
        "/routing/decide",
        json={"privacy_required": False, "required_capabilities": ["external"]},
    )

    assert providers_response.status_code == 200
    external_provider = next(
        provider
        for provider in providers_response.json()
        if provider["id"] == provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    )
    assert external_provider["enabled"] is False
    assert external_provider["base_url"] is None
    assert external_provider["model_names"] == []
    assert health_response.status_code == 200
    assert health_response.json()["available"] is False
    assert route_response.status_code == 404
    assert calls == []
    assert "external-api-key-secret" not in (
        providers_response.text + health_response.text + route_response.text
    )
    get_settings.cache_clear()


def test_provider_health_uses_shared_transport_without_retry(monkeypatch) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise HTTPError(
            request.full_url,
            503,
            "Unavailable",
            {},
            BytesIO(b'{"token":"health-error-secret"}'),
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)
    client = TestClient(create_app())

    response = client.get("/providers/ollama/health")

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert calls == ["http://127.0.0.1:11434/api/tags"]
    assert sleeps == []
    assert "health-error-secret" not in response.text


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
    assert create_response.json()["requested_by"] == sha256(token.encode("utf-8")).hexdigest()[:12]
    assert approve_response.status_code == 200
    assert approve_response.json()["decided_by"] == sha256(token.encode("utf-8")).hexdigest()[:12]
    get_settings.cache_clear()


def test_cli_approval_direct_execute_requires_bound_authenticated_requester(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    requester_token = "cli-requester-token"
    executor_token = "cli-executor-token"
    requester_actor = sha256(requester_token.encode("utf-8")).hexdigest()[:12]
    executor_actor = sha256(executor_token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        f"{requester_token}=cli,logs;{executor_token}=cli,logs",
    )
    get_settings.cache_clear()
    client = TestClient(create_app())
    requester_headers = {"Authorization": f"Bearer {requester_token}"}
    executor_headers = {"Authorization": f"Bearer {executor_token}"}

    create_response = client.post(
        "/cli/approvals?requested_by=spoofed-query-actor",
        json={"command": "python --version", "timeout_seconds": 10},
        headers=requester_headers,
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
        headers=requester_headers,
    )
    cross_execute_response = client.post(
        f"/cli/approvals/{approval_id}/execute",
        headers=executor_headers,
    )
    execute_response = client.post(
        f"/cli/approvals/{approval_id}/execute",
        headers=requester_headers,
    )
    logs_response = client.get("/logs?event_type=cli", headers=requester_headers)

    assert create_response.status_code == 201
    assert create_response.json()["requested_by"] == requester_actor
    assert approve_response.status_code == 200
    assert cross_execute_response.status_code == 403
    assert "different requester" in cross_execute_response.json()["detail"]
    assert executor_actor not in logs_response.text
    assert execute_response.status_code == 200
    assert execute_response.json()["requested_by"] == requester_actor
    assert any(
        event["message"] == "Recorded CLI command run." and event["actor"] == requester_actor
        for event in logs_response.json()
    )
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


def test_cli_runs_api_uses_authenticated_principal_over_body_requested_by(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    token = "cli-run-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=cli,logs")
    get_settings.cache_clear()
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    start_response = client.post(
        "/cli/runs",
        headers=headers,
        json={
            "command": "cmd /c echo principal-run",
            "approved": True,
            "timeout_seconds": 10,
            "requested_by": "spoofed-body-actor",
        },
    )
    run_id = start_response.json()["id"]

    assert start_response.status_code == 202
    assert start_response.json()["requested_by"] == actor_id

    for _attempt in range(40):
        final_response = client.get(f"/cli/runs/{run_id}", headers=headers)
        if final_response.json()["completed_at"] is not None:
            break
        time.sleep(0.1)
    else:
        raise AssertionError("Authenticated API command run did not finalize.")

    logs_response = client.get("/logs?event_type=cli", headers=headers)

    assert final_response.json()["requested_by"] == actor_id
    assert "principal-run" in final_response.json()["stdout"]
    assert "spoofed-body-actor" not in final_response.text + logs_response.text
    assert any(
        event["subject_id"] == run_id and event["actor"] == actor_id
        for event in logs_response.json()
    )
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


def test_cli_policy_api_uses_authenticated_principal_as_audit_actor(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    token = "cli-policy-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=cli,logs")
    get_settings.cache_clear()
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/cli/policy/rules",
        headers=headers,
        json={
            "name": "Audit block unsafe flag",
            "match_type": "argument_contains",
            "pattern": "--audit-unsafe",
            "permission_mode": "blocked",
            "reason": "Unsafe audit flag is blocked.",
            "priority": 5,
        },
    )
    rule_id = create_response.json()["id"]
    decision_response = client.post(
        "/guardrails/commands",
        headers=headers,
        json={"command": "cmd /c echo --audit-unsafe"},
    )
    update_response = client.patch(
        f"/cli/policy/rules/{rule_id}",
        headers=headers,
        json={"enabled": False},
    )
    logs_response = client.get("/logs?event_type=cli", headers=headers)

    assert create_response.status_code == 201
    assert decision_response.status_code == 200
    assert decision_response.json()["matched_rule_id"] == rule_id
    assert update_response.status_code == 200
    assert any(
        event["message"] == "Created CLI command policy rule." and event["actor"] == actor_id
        for event in logs_response.json()
    )
    assert any(
        event["message"] == "Evaluated CLI command policy." and event["actor"] == actor_id
        for event in logs_response.json()
    )
    assert any(
        event["message"] == "Updated CLI command policy rule." and event["actor"] == actor_id
        for event in logs_response.json()
    )
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


def test_cli_execute_api_uses_authenticated_principal_over_body_requested_by(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    token = "cli-execute-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=cli,logs")
    get_settings.cache_clear()
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/cli/execute",
        headers=headers,
        json={
            "command": "cmd /c echo principal-execute",
            "approved": True,
            "requested_by": "spoofed-body-actor",
        },
    )
    logs_response = client.get("/logs?event_type=cli", headers=headers)

    assert response.status_code == 200
    assert response.json()["requested_by"] == actor_id
    assert "principal-execute" in response.json()["stdout"]
    assert "spoofed-body-actor" not in response.text + logs_response.text
    assert any(
        event["message"] == "Recorded CLI command run." and event["actor"] == actor_id
        for event in logs_response.json()
    )
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


@pytest.mark.parametrize(
    "command",
    [
        "../outside-tool --version",
        "/bin/cat README.md",
        r"C:\Windows\System32\whoami.exe",
        r"cmd /c ..\outside-tool --version",
        'powershell -Command "Start-Process -FilePath ../outside-tool -ArgumentList --version"',
    ],
)
def test_command_guardrail_api_blocks_executable_paths_outside_root(
    tmp_path,
    monkeypatch,
    command: str,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post("/guardrails/commands", json={"command": command})

    assert response.status_code == 200
    assert response.json()["permission_mode"] == "blocked"
    assert "executable path resolves outside configured rootDir" in response.json()["reason"]
    get_settings.cache_clear()


def test_cli_execute_api_blocks_executable_path_escape_before_launch(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post(
        "/cli/execute",
        json={"command": "../outside-tool --version", "timeout_seconds": 5},
    )
    runs_response = client.get("/cli/runs")

    assert response.status_code == 403
    assert "executable path resolves outside configured rootDir" in response.json()["detail"]
    assert runs_response.json() == []
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "environment_key",
    ["PATH", "BASH_ENV", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS"],
)
def test_cli_execute_api_rejects_blocked_environment_override(
    tmp_path,
    monkeypatch,
    environment_key: str,
) -> None:
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
            "environment": {environment_key: "C:\\unsafe"},
        },
    )

    assert response.status_code == 400
    assert environment_key in response.json()["detail"]
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
    assert body["results"][0]["source_type"] == "metadata_text_fallback"
    assert set(body["results"][0]["matched_fields"]) >= {"metadata_text", "tags"}
    assert "embedding_source=metadata_text_fallback" in body["results"][0]["score_reasons"]
    get_settings.cache_clear()


def test_memory_lifecycle_api_previews_applies_and_excludes_inactive(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())

    create_response = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "stale-memory",
            "tags": ["lifecycle"],
            "category": "retrieval",
            "description": "Lifecycle-managed metadata retrieval candidate.",
            "relevance_score": 0.3,
        },
    )
    preview_response = client.post(
        "/api/v1/memory/lifecycle/preview",
        json={"reference_time": "2027-01-01T00:00:00+00:00"},
    )
    apply_response = client.post(
        "/api/v1/memory/lifecycle/apply",
        json={"reference_time": "2027-01-01T00:00:00+00:00"},
    )
    default_retrieval_response = client.post(
        "/api/v1/memory/retrieve/hybrid",
        json={
            "query": "lifecycle managed metadata retrieval candidate",
            "metadata_filters": {"category": "retrieval"},
            "similarity_threshold": 0.0,
        },
    )
    inactive_retrieval_response = client.post(
        "/api/v1/memory/retrieve/hybrid",
        json={
            "query": "lifecycle managed metadata retrieval candidate",
            "metadata_filters": {"category": "retrieval"},
            "similarity_threshold": 0.0,
            "include_inactive": True,
        },
    )
    archived_list_response = client.get("/api/v1/memory/metadata?lifecycle_state=archived")

    assert create_response.status_code == 201
    assert preview_response.status_code == 200
    assert preview_response.json()["applied"] is False
    assert preview_response.json()["decisions"][0]["recommended_action"] == "archive"
    assert apply_response.status_code == 200
    assert apply_response.json()["applied"] is True
    assert apply_response.json()["decisions"][0]["recommended_action"] == "archive"
    assert default_retrieval_response.status_code == 200
    assert default_retrieval_response.json()["total"] == 0
    assert inactive_retrieval_response.status_code == 200
    assert inactive_retrieval_response.json()["total"] == 1
    assert inactive_retrieval_response.json()["results"][0]["entity_id"] == "stale-memory"
    assert archived_list_response.status_code == 200
    assert archived_list_response.json()["total"] == 1


def test_memory_compression_api_applies_and_retrieves_compressed_metadata(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    long_description = (
        "This memory has been used repeatedly by agents while planning retrieval work. "
        "It contains implementation context, validation notes, and follow-up details that "
        "can be summarized into a shorter durable record without losing its purpose."
    )

    create_response = client.post(
        "/api/v1/memory/metadata",
        json={
            "entity_type": "memory",
            "entity_id": "compress-api-memory",
            "tags": ["compression", "retrieval"],
            "category": "planning",
            "description": long_description,
            "relevance_score": 0.6,
        },
    )
    metadata_id = create_response.json()["id"]
    session = get_db_session()
    try:
        stored = session.query(MemoryMetadata).filter(MemoryMetadata.id == metadata_id).one()
        stored.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        stored.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
        stored.access_count = 15
        session.commit()
    finally:
        session.close()

    preview_response = client.post(
        "/api/v1/memory/compression/preview",
        json={
            "category": "planning",
            "reference_time": "2026-02-15T00:00:00+00:00",
            "max_summary_chars": 120,
        },
    )
    apply_response = client.post(
        "/api/v1/memory/compression/apply",
        json={
            "category": "planning",
            "reference_time": "2026-02-15T00:00:00+00:00",
            "max_summary_chars": 120,
        },
    )
    get_response = client.get(f"/api/v1/memory/metadata/{metadata_id}")
    retrieval_response = client.post(
        "/api/v1/memory/retrieve/hybrid",
        json={
            "query": "planning retrieval work",
            "metadata_filters": {"category": "planning"},
            "similarity_threshold": 0.0,
        },
    )

    assert create_response.status_code == 201
    assert preview_response.status_code == 200
    assert preview_response.json()["applied"] is False
    assert preview_response.json()["total"] == 1
    assert apply_response.status_code == 200
    assert apply_response.json()["applied"] is True
    assert apply_response.json()["total"] == 1
    candidate = apply_response.json()["candidates"][0]
    assert candidate["compressed_length"] < candidate["original_length"]
    assert get_response.status_code == 200
    assert get_response.json()["description"] == candidate["compressed_description"]
    assert get_response.json()["last_compacted_at"] is not None
    assert retrieval_response.status_code == 200
    assert retrieval_response.json()["total"] == 1
    assert retrieval_response.json()["results"][0]["entity_id"] == "compress-api-memory"


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


def test_dynamic_tool_generation_requires_newer_overwrite_for_version_migration(
    isolated_tool_api_state,
) -> None:
    root_dir = isolated_tool_api_state
    client = TestClient(create_app())

    first_response = client.post(
        "/tools/generate",
        json={
            "name": "versioned-tool",
            "version": "1.0.0",
            "description": "Version one.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": "def run(payload):\n    return {'version': 'v1'}\n",
            "interface": {"input": "dict", "output": "v1"},
        },
    )
    stale_response = client.post(
        "/tools/generate",
        json={
            "name": "versioned-tool",
            "version": "1.0.0",
            "description": "Same version should be blocked.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "overwrite": True,
            "source_code": "def run(payload):\n    return {'version': 'stale'}\n",
            "interface": {"input": "dict", "output": "stale"},
        },
    )
    missing_policy_response = client.post(
        "/tools/generate",
        json={
            "name": "versioned-tool",
            "version": "1.1.0",
            "description": "Newer version still requires explicit overwrite.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": "def run(payload):\n    return {'version': 'blocked'}\n",
            "interface": {"input": "dict", "output": "blocked"},
        },
    )
    registry_response = client.get("/api/v1/tools/registry?permission_level=autopilot_safe")
    registry_tool = next(
        item for item in registry_response.json()["items"] if item["tool_name"] == "versioned-tool"
    )
    usage_response = client.post(
        f"/api/v1/tools/registry/{registry_tool['id']}/usage",
        json={"status": "failure", "execution_time_ms": 25},
    )
    tool_path = root_dir / "localmcp" / "versioned-tool" / "tool.py"
    manifest_path = root_dir / "localmcp" / "versioned-tool" / "manifest.json"
    pre_migration_source = tool_path.read_text(encoding="utf-8")

    assert first_response.status_code == 201
    assert stale_response.status_code == 409
    assert missing_policy_response.status_code == 409
    assert "v1" in pre_migration_source
    assert "stale" not in pre_migration_source
    assert "blocked" not in pre_migration_source
    assert usage_response.status_code == 200
    assert usage_response.json()["usage_count"] == 1

    migration_response = client.post(
        "/tools/generate",
        json={
            "name": "versioned-tool",
            "version": "1.1.0",
            "description": "Version two.",
            "trigger_source": "skill",
            "permission_mode": "approval_required",
            "tags": ["migrated"],
            "overwrite": True,
            "source_code": "def run(payload):\n    return {'version': 'v2'}\n",
            "interface": {"input": "dict", "output": "v2"},
        },
    )
    migrated_registry_response = client.get("/api/v1/tools/registry")
    tools_response = client.get("/tools")

    assert migration_response.status_code == 201
    assert migration_response.json()["duplicate_detected"] is True
    migrated_manifest = migration_response.json()["manifest"]
    assert migrated_manifest["version"] == "1.1.0"
    assert migrated_manifest["permission_mode"] == "approval_required"
    assert "v2" in tool_path.read_text(encoding="utf-8")
    assert "Version: `1.1.0`" in (root_dir / "localmcp" / "versioned-tool" / "README.md").read_text(
        encoding="utf-8"
    )
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["version"] == "1.1.0"
    assert [tool["name"] for tool in tools_response.json() if tool["name"] == "versioned-tool"] == [
        "versioned-tool"
    ]

    migrated_items = [
        item
        for item in migrated_registry_response.json()["items"]
        if item["tool_name"] == "versioned-tool"
    ]
    assert len(migrated_items) == 1
    migrated_registry_tool = migrated_items[0]
    assert migrated_registry_tool["id"] == registry_tool["id"]
    assert migrated_registry_tool["version"] == "1.1.0"
    assert migrated_registry_tool["permission_level"] == "approval_required"
    assert migrated_registry_tool["tags"] == ["migrated", "skill"]
    assert migrated_registry_tool["usage_count"] == 0
    assert migrated_registry_tool["success_count"] == 0
    assert migrated_registry_tool["failure_count"] == 0
    assert migrated_registry_tool["reliability_score"] == 1.0
    assert migrated_registry_tool["deprecated"] is False


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


def test_generated_tool_execute_api_serializes_orchestration_decisions(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Bind tool execution to the scheduled QA task.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Evaluate orchestration-bound tool execution.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Tool binding is enforced.",
                }
            ],
        },
    )
    task = create_response.json()["tasks"][0]
    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-orchestration-tool",
            "description": "Serialize orchestration action decisions.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": "def run(payload):\n    return {'ok': True}\n",
        },
    )
    execute_response = client.post(
        "/tools/api-orchestration-tool/execute",
        json={
            "payload": {},
            "agent_id": task["agent_id"],
            "agent_role": task["role"],
            "task_id": task["id"],
        },
    )
    logs_response = client.get("/logs?event_type=tool")

    expected_orchestration = {
        "allowed": True,
        "reason": "Tool action is bound to a running orchestration task.",
        "run_id": create_response.json()["id"],
        "task_id": task["id"],
        "agent_id": task["agent_id"],
        "agent_role": task["role"],
        "violating_paths": [],
    }
    assert create_response.status_code == 201
    assert generate_response.status_code == 201
    assert execute_response.status_code == 200
    assert execute_response.json()["orchestration"] == expected_orchestration
    execution_event = [
        event for event in logs_response.json() if event["subject_id"] == "api-orchestration-tool"
    ][-1]
    assert execution_event["metadata"]["orchestration"] == expected_orchestration
    get_settings.cache_clear()


def test_generated_tool_api_blocks_partial_active_orchestration_context(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Block partial generated-tool context for active QA task.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate API tool orchestration binding.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Tool runtime binding is enforced.",
                }
            ],
        },
    )
    task = create_response.json()["tasks"][0]
    approval_generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-partial-approval-tool",
            "description": "Reject partial active approval context.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": "def run(payload):\n    return {'approval_ok': True}\n",
        },
    )
    execute_response = client.post(
        "/tools/api-partial-approval-tool/execute",
        json={
            "payload": {},
            "agent_id": task["agent_id"],
        },
    )
    role_only_execute_response = client.post(
        "/tools/api-partial-approval-tool/execute",
        json={
            "payload": {},
            "agent_role": task["role"],
        },
    )
    approval_response = client.post(
        "/tools/api-partial-approval-tool/approvals?requested_by=tester",
        json={
            "payload": {},
            "task_id": task["id"],
        },
    )
    role_only_approval_response = client.post(
        "/tools/api-partial-approval-tool/approvals?requested_by=tester",
        json={
            "payload": {},
            "agent_role": task["role"],
        },
    )

    assert create_response.status_code == 201
    assert approval_generate_response.status_code == 201
    assert execute_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in execute_response.json()["detail"]
    assert role_only_execute_response.status_code == 403
    assert (
        "require agent_id, agent_role, and task_id" in role_only_execute_response.json()["detail"]
    )
    assert approval_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in approval_response.json()["detail"]
    assert role_only_approval_response.status_code == 403
    assert (
        "require agent_id, agent_role, and task_id" in role_only_approval_response.json()["detail"]
    )
    get_settings.cache_clear()


def test_generated_tool_api_redacts_orchestration_denial_reason(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Redact generated-tool orchestration denial context.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate API denial redaction.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Tool runtime binding redacts denial context.",
                }
            ],
        },
    )
    task = create_response.json()["tasks"][0]
    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-redacted-denial-tool",
            "description": "Redact orchestration denial context.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": "def run(payload):\n    return {'ok': True}\n",
        },
    )
    execute_response = client.post(
        "/tools/api-redacted-denial-tool/execute",
        json={
            "payload": {},
            "agent_id": task["agent_id"],
            "agent_role": "Developer SECRET=api-role-leak",
            "task_id": task["id"],
        },
    )

    assert create_response.status_code == 201
    assert generate_response.status_code == 201
    assert execute_response.status_code == 403
    assert "api-role-leak" not in execute_response.text
    assert "SECRET=[REDACTED]" in execute_response.text
    get_settings.cache_clear()


def test_approved_generated_tool_execution_rechecks_active_orchestration_context(
    isolated_tool_api_state,
) -> None:
    client = TestClient(create_app())
    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-approval-recheck-tool",
            "description": "Recheck orchestration context before execution.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": "def run(payload):\n    return {'ok': True}\n",
        },
    )
    approval_response = client.post(
        "/tools/api-approval-recheck-tool/approvals?requested_by=tester",
        json={
            "payload": {},
            "task_id": "qa-validation",
        },
    )
    approval_id = approval_response.json()["id"]
    create_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Recheck active context before generated-tool execution.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate approved generated-tool binding.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Approved generated-tool execution is rechecked.",
                }
            ],
        },
    )
    approve_response = client.post(
        f"/tools/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
    )
    execute_response = client.post(
        "/tools/api-approval-recheck-tool/execute",
        json={
            "payload": {},
            "approval_id": approval_id,
            "task_id": "qa-validation",
        },
    )

    assert generate_response.status_code == 201
    assert approval_response.status_code == 201
    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert execute_response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in execute_response.json()["detail"]
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


def test_generated_tool_execute_api_uses_authenticated_principal_over_body_requested_by(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    token = "tool-execute-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "true")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=tools,logs")
    get_settings.cache_clear()
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    generate_response = client.post(
        "/tools/generate",
        headers=headers,
        json={
            "name": "api-principal-tool",
            "description": "Records authenticated execution principal.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": "def run(payload):\n    return {'value': payload.get('value')}\n",
        },
    )
    execute_response = client.post(
        "/tools/api-principal-tool/execute",
        headers=headers,
        json={
            "payload": {"value": "principal-tool"},
            "requested_by": "spoofed-body-actor",
            "timeout_seconds": 5,
        },
    )
    logs_response = client.get("/logs?event_type=tool", headers=headers)

    assert generate_response.status_code == 201
    assert execute_response.status_code == 200
    assert execute_response.json()["parsed_output"]["value"] == "principal-tool"
    assert "spoofed-body-actor" not in execute_response.text + logs_response.text
    assert any(
        event["message"] == "Executed generated tool."
        and event["actor"] == actor_id
        and event["metadata"]["requested_by"] == actor_id
        for event in logs_response.json()
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


def test_generated_tool_execute_api_enforces_network_domain_policy(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "blocked.example.test",
                        "mode": "deny",
                    }
                ]
            }
        ),
    )
    get_settings.cache_clear()
    client = TestClient(create_app())

    generate_response = client.post(
        "/tools/generate",
        json={
            "name": "api-network-denied-tool",
            "description": "Attempts outbound network access.",
            "trigger_source": "main_agent",
            "permission_mode": "autopilot_safe",
            "source_code": (
                "import socket\n\n"
                "def run(payload):\n"
                "    socket.create_connection(('blocked.example.test', 443), timeout=1)\n"
                "    return {'ok': True}\n"
            ),
        },
    )
    execute_response = client.post(
        "/tools/api-network-denied-tool/execute",
        json={"payload": {}, "timeout_seconds": 5},
    )

    assert generate_response.status_code == 201
    assert execute_response.status_code == 200
    body = execute_response.json()
    assert body["exit_code"] == 1
    assert body["stdout"] == ""
    assert body["parsed_output"] is None
    assert "blocked by DGentic network policy" in body["stderr"]
    get_settings.cache_clear()


def test_provider_generate_api_rejects_unsupported_provider() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "unknown",
            "model": "local-model",
            "messages": [{"role": "user", "content": "prompt-secret-123"}],
        },
    )

    assert response.status_code == 400


def test_provider_generate_api_blocks_partial_active_orchestration_context(
    isolated_tool_api_state,
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())
    create_run_response = client.post(
        "/tasks/orchestrations",
        json={
            "objective": "Block partial provider context.",
            "tasks": [
                {
                    "id": "qa-validation",
                    "title": "QA validation",
                    "description": "Validate provider context binding.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_api.py"],
                    "validation": "Provider context is verified.",
                }
            ],
        },
    )
    task = create_run_response.json()["tasks"][0]

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "messages": [{"role": "user", "content": "hello"}],
            "agent_id": task["agent_id"],
        },
    )

    assert create_run_response.status_code == 201
    assert response.status_code == 403
    assert "require agent_id, agent_role, and task_id" in response.json()["detail"]
    assert calls == []
    get_settings.cache_clear()


@pytest.mark.parametrize("path", ["/providers/generate", "/providers/generate/stream"])
def test_provider_generate_api_returns_422_for_invalid_payload_before_transport(
    path,
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append(url)
        return {}

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        path,
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "messages": [{"role": "invalid", "content": "TOKEN=validation-secret"}],
            "options": {"api_key": "validation-option-secret"},
        },
    )

    assert response.status_code == 422
    assert calls == []
    assert "validation-secret" not in response.text
    assert "validation-option-secret" not in response.text


def test_provider_generate_api_rejects_disallowed_base_url_before_post(
    monkeypatch,
) -> None:
    calls: list[dict] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {}

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "ollama",
            "model": "llama3.1",
            "base_url": "http://169.254.169.254/latest",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 403
    assert calls == []
    assert "169.254.169.254" not in response.text


def test_provider_generate_api_sanitizes_os_permission_errors(monkeypatch) -> None:
    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        raise PermissionError("access denied: C:/secret/provider-key.txt")

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    assert "provider-key" not in response.text


def test_provider_generate_api_allows_extra_trusted_base_url(monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_ALLOWED_BASE_URLS", "http://127.0.0.1:4321")
    get_settings.cache_clear()
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-extra-api",
        "model": "local-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Extra API endpoint."},
                "finish_reason": "stop",
            }
        ],
    }

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return raw_response

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:4321",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Extra API endpoint."
    assert calls == [
        {
            "url": "http://127.0.0.1:4321/v1/chat/completions",
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            "timeout_seconds": 60.0,
        }
    ]
    get_settings.cache_clear()


def test_provider_generate_api_rejects_streaming_before_post(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {}

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 501
    assert calls == []


def test_provider_generate_stream_api_emits_ordered_ndjson_and_safe_logs(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
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
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-api-stream",
                    "model": "local-model",
                    "choices": [{"index": 0, "delta": {"content": "Hel"}, "finish_reason": None}],
                },
                {
                    "id": "chatcmpl-api-stream",
                    "model": "local-model",
                    "choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": None}],
                },
                {
                    "id": "chatcmpl-api-stream",
                    "model": "local-model",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
                {
                    "id": "chatcmpl-api-stream",
                    "model": "local-model",
                    "choices": [],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
                },
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
            "max_tokens": 32,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert calls == [
        {
            "url": "http://127.0.0.1:1234/v1/chat/completions",
            "headers": {"Accept": "text/event-stream", "Content-type": "application/json"},
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
                "temperature": 0.2,
                "max_tokens": 32,
            },
            "timeout_seconds": 60.0,
        }
    ]
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["delta"] for event in events] == ["Hel", "lo", "", ""]
    assert events[-2]["finish_reason"] == "stop"
    assert events[-2]["estimated_cost_usd"] is None
    assert events[-1]["usage_metadata"] == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert events[-1]["estimated_cost_usd"] == 0.0
    assert "Hello" not in logs_response.text
    get_settings.cache_clear()


def test_provider_generate_stream_api_emits_ollama_ndjson_and_safe_logs(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
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
        return FakeStreamResponse(
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

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "ollama",
            "model": "llama3.1",
            "base_url": "http://127.0.0.1:11434",
            "messages": [{"role": "user", "content": "prompt-secret-123"}],
            "temperature": 0.2,
            "max_tokens": 32,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert calls == [
        {
            "url": "http://127.0.0.1:11434/api/chat",
            "headers": {"Accept": "application/x-ndjson", "Content-type": "application/json"},
            "payload": {
                "model": "llama3.1",
                "messages": [{"role": "user", "content": "prompt-secret-123"}],
                "options": {"temperature": 0.2, "num_predict": 32},
                "stream": True,
            },
            "timeout_seconds": 60.0,
        }
    ]
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["delta"] for event in events] == ["delta-secret-", "abc", ""]
    assert events[-1]["finish_reason"] == "stop"
    assert events[-1]["usage_metadata"] == {
        "prompt_tokens": 4,
        "completion_tokens": 2,
        "total_tokens": 6,
    }
    assert events[-1]["estimated_cost_usd"] == 0.0
    assert "prompt-secret-123" not in logs_response.text
    assert "delta-secret-abc" not in logs_response.text
    assert "delta-secret-" not in logs_response.text
    get_settings.cache_clear()


def test_provider_generate_stream_api_maps_ollama_error_first_chunk_to_bad_gateway(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse([json.dumps({"error": "ollama-upstream-error-secret"}) + "\n"])

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "ollama",
            "model": "llama3.1",
            "base_url": "http://127.0.0.1:11434",
            "messages": [{"role": "user", "content": "prompt-secret-123"}],
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    serialized = response.text + logs_response.text
    assert "ollama-upstream-error-secret" not in serialized
    assert "prompt-secret-123" not in serialized
    get_settings.cache_clear()


def test_provider_generate_stream_api_emits_sanitized_error_for_ollama_post_chunk_error(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()

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

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "ollama",
            "model": "llama3.1",
            "base_url": "http://127.0.0.1:11434",
            "messages": [{"role": "user", "content": "prompt-secret-123"}],
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["delta"] for event in events] == ["delta-secret-abc", ""]
    assert events[-1]["event"] == "error"
    assert events[-1]["error"] == "Provider request failed."
    serialized_logs = logs_response.text
    assert "delta-secret-abc" not in serialized_logs
    assert "ollama-upstream-error-secret" not in serialized_logs
    assert "prompt-secret-123" not in serialized_logs
    get_settings.cache_clear()


def test_external_provider_generate_stream_api_sends_authorization_and_redacts_logs(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
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
                    "id": "chatcmpl-external-stream-api",
                    "model": "gpt-test",
                    "choices": [
                        {"index": 0, "delta": {"content": "External"}, "finish_reason": None}
                    ],
                    "token": "upstream-stream-token-secret",
                },
                {
                    "id": "chatcmpl-external-stream-api",
                    "model": "gpt-test",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        }
    ]
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["delta"] for event in events] == ["External", ""]
    serialized = response.text + logs_response.text
    assert "external-api-key-secret" not in serialized
    assert "upstream-stream-token-secret" not in serialized
    assert "External" in response.text
    assert "External" not in logs_response.text
    get_settings.cache_clear()


def test_external_provider_generate_stream_api_uses_authenticated_principal_as_audit_actor(
    tmp_path,
    monkeypatch,
) -> None:
    token = "provider-stream-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "true")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=providers,logs")
    configure_external_provider_api(monkeypatch)
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-stream-principal",
                    "model": "gpt-test",
                    "choices": [
                        {"index": 0, "delta": {"content": "Principal"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "chatcmpl-stream-principal",
                    "model": "gpt-test",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/providers/generate/stream",
        headers=headers,
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
            "requested_by": "spoofed-body-actor",
        },
    )
    logs_response = client.get("/logs?event_type=provider", headers=headers)

    assert response.status_code == 200
    assert calls == ["https://provider.example.test/v1/chat/completions"]
    assert "Principal" in response.text
    assert "spoofed-body-actor" not in response.text + logs_response.text
    assert any(
        event["message"] == "Started provider streaming generation."
        and event["actor"] == actor_id
        and event["metadata"]["requested_by"] == actor_id
        for event in logs_response.json()
    )
    assert any(
        event["message"] == "Completed provider streaming generation."
        and event["actor"] == actor_id
        for event in logs_response.json()
    )
    get_settings.cache_clear()


def test_external_provider_generate_stream_api_returns_configured_model_cost(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": 0.5,
                        "completion_usd_per_1k_tokens": 1.0,
                        "request_estimate_usd": 0.02,
                    }
                }
            }
        ),
    )
    configure_external_provider_api(monkeypatch)

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-external-stream-api",
                    "model": "provider-controlled-model-secret",
                    "choices": [
                        {"index": 0, "delta": {"content": "Priced"}, "finish_reason": None}
                    ],
                },
                {
                    "id": "chatcmpl-external-stream-api",
                    "model": "provider-controlled-model-secret",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
                {
                    "id": "chatcmpl-external-stream-api",
                    "model": "provider-controlled-model-secret",
                    "choices": [],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
                },
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["model"] == "gpt-test"
    assert events[-1]["estimated_cost_usd"] == 0.009
    serialized = response.text + logs_response.text
    assert "external-api-key-secret" not in serialized
    assert "provider-controlled-model-secret" not in logs_response.text
    assert "Priced" in response.text
    assert "Priced" not in logs_response.text
    get_settings.cache_clear()


def test_external_provider_generate_stream_api_requires_approval_before_transport(
    monkeypatch,
) -> None:
    configure_external_provider_api(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello TOKEN=stream-prompt-secret"}],
        },
    )

    assert response.status_code == 403
    assert calls == []
    assert blocked_credentials.calls == []
    assert "stream-prompt-secret" not in response.text
    get_settings.cache_clear()


def test_external_provider_generate_stream_api_accepts_bound_approval_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    tracked_credentials = TrackingCredentialEnviron(
        key="DGENTIC_TEST_EXTERNAL_API_KEY",
        value="external-api-key-secret",
    )
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
                    "id": "chatcmpl-stream-approval-api",
                    "model": "gpt-test",
                    "choices": [
                        {"index": 0, "delta": {"content": "Approved"}, "finish_reason": None}
                    ],
                    "token": "upstream-stream-token-secret",
                },
                {
                    "id": "chatcmpl-stream-approval-api",
                    "model": "gpt-test",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)
    client = TestClient(create_app())
    provider_id = provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    approval_body = {
        "provider_id": provider_id,
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "stream hello"}],
        "stream": True,
        "requested_by": "tester",
    }
    bypass_response = client.post(
        "/providers/generate/stream",
        json={**approval_body, "approved": True},
    )
    create_response = client.post(
        f"/providers/{provider_id}/approvals",
        json=approval_body,
    )
    approval_id = create_response.json()["id"]
    approve_response = client.post(
        f"/providers/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer"},
    )
    monkeypatch.setattr(provider_runtime, "environ", tracked_credentials)
    response = client.post(
        "/providers/generate/stream",
        json={**approval_body, "stream": False, "approval_id": approval_id},
    )
    second_response = client.post(
        "/providers/generate/stream",
        json={**approval_body, "stream": False, "approval_id": approval_id},
    )
    logs_response = client.get("/logs?event_type=provider")

    assert bypass_response.status_code == 403
    assert "approval_id" in bypass_response.json()["detail"]
    assert create_response.status_code == 201
    assert approve_response.status_code == 200
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert second_response.status_code == 403
    assert "not executable" in second_response.json()["detail"]
    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "stream hello"}],
                "stream": True,
            },
        }
    ]
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["delta"] for event in events] == ["Approved", ""]
    serialized = response.text + logs_response.text
    assert "external-api-key-secret" not in serialized
    assert "upstream-stream-token-secret" not in serialized
    assert "Approved" in response.text
    assert "Approved" not in logs_response.text
    assert blocked_credentials.calls == []
    assert tracked_credentials.calls == ["DGENTIC_TEST_EXTERNAL_API_KEY"]
    get_settings.cache_clear()


def test_external_provider_generate_stream_api_missing_config_fails_before_transport(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "DGENTIC_TEST_EXTERNAL")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    monkeypatch.setenv("DGENTIC_TEST_EXTERNAL", "external-api-key-secret")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "External provider is not configured."
    assert calls == []
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_provider_generate_stream_api_rejects_external_placeholder(monkeypatch) -> None:
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "external-placeholder",
            "model": "external-default",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 501
    assert calls == []


def test_provider_generate_stream_api_maps_malformed_first_chunk_to_bad_gateway(
    monkeypatch,
) -> None:
    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(['data: {"not": "valid"\n'])

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."


def test_provider_generate_stream_api_maps_malformed_success_chunk_to_bad_gateway(
    monkeypatch,
) -> None:
    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            openai_stream_lines(
                {"choices": [{"index": 0, "delta": {"content": {"secret": "stream-content"}}}]}
            )
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    assert "stream-upstream-secret" not in response.text
    assert "stream-content" not in response.text


def test_provider_generate_stream_api_emits_sanitized_error_after_first_chunk(
    monkeypatch,
) -> None:
    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeStreamResponse(
            openai_stream_lines(
                {
                    "id": "chatcmpl-api-stream",
                    "model": "local-model",
                    "choices": [
                        {"index": 0, "delta": {"content": "Visible"}, "finish_reason": None}
                    ],
                },
                done=False,
            )
            + ['data: {"not": "valid"\n']
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate/stream",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["delta"] == "Visible"
    assert events[-1]["event"] == "error"
    assert events[-1]["error"] == "Provider request failed."


def test_provider_generate_api_rejects_external_placeholder_before_post(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return {}

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "external-placeholder",
            "model": "external-default",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 501
    assert calls == []


def test_external_provider_generate_api_sends_authorization_and_redacts_logs(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-external-api",
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello external API."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        "token": "upstream-token-secret",
        "authorization": "Bearer upstream-auth-secret",
    }

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(raw_response).encode("utf-8")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return FakeResponse()

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
            "max_tokens": 32,
            "approved": True,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 32,
            },
        }
    ]
    assert response.json()["content"] == "Hello external API."
    assert response.json()["usage_metadata"] == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }
    assert response.json()["estimated_cost_usd"] == 0.01
    serialized = response.text + logs_response.text
    for raw_secret in [
        "external-api-key-secret",
        "upstream-token-secret",
        "upstream-auth-secret",
    ]:
        assert raw_secret not in serialized
    assert "Hello external API." in response.text
    assert "Hello external API." not in logs_response.text
    get_settings.cache_clear()


def test_external_provider_generate_api_uses_authenticated_principal_as_audit_actor(
    tmp_path,
    monkeypatch,
) -> None:
    token = "provider-direct-principal-token"
    actor_id = sha256(token.encode("utf-8")).hexdigest()[:12]
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "true")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", f"{token}=providers,logs")
    configure_external_provider_api(monkeypatch)
    calls: list[str] = []
    raw_response = {
        "id": "chatcmpl-direct-principal",
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Principal response."},
                "finish_reason": "stop",
            }
        ],
    }

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(raw_response).encode("utf-8")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/providers/generate",
        headers=headers,
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
            "requested_by": "spoofed-body-actor",
        },
    )
    logs_response = client.get("/logs?event_type=provider", headers=headers)

    assert response.status_code == 200
    assert response.json()["content"] == "Principal response."
    assert calls == ["https://provider.example.test/v1/chat/completions"]
    assert "spoofed-body-actor" not in response.text + logs_response.text
    assert any(
        event["message"] == "Started provider generation."
        and event["actor"] == actor_id
        and event["metadata"]["requested_by"] == actor_id
        for event in logs_response.json()
    )
    assert any(
        event["message"] == "Completed provider generation." and event["actor"] == actor_id
        for event in logs_response.json()
    )
    get_settings.cache_clear()


def test_external_provider_generate_api_returns_configured_model_cost(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "DGENTIC_PROVIDER_PRICING_CATALOG",
        json.dumps(
            {
                provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID: {
                    "gpt-test": {
                        "prompt_usd_per_1k_tokens": 0.5,
                        "completion_usd_per_1k_tokens": 1.0,
                        "request_estimate_usd": 0.02,
                    }
                }
            }
        ),
    )
    configure_external_provider_api(monkeypatch)
    raw_response = {
        "id": "chatcmpl-external-api",
        "model": "provider-controlled-model-secret",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Priced external API."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
    }

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(raw_response).encode("utf-8")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        return FakeResponse()

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    assert response.json()["estimated_cost_usd"] == 0.009
    assert "Priced external API." in response.text
    serialized_logs = logs_response.text
    assert "external-api-key-secret" not in response.text + serialized_logs
    assert "provider-controlled-model-secret" not in response.text + serialized_logs
    assert "Priced external API." not in serialized_logs
    get_settings.cache_clear()


def test_external_provider_generate_api_rejects_invalid_pricing_before_transport(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_PROVIDER_PRICING_CATALOG", "not-json")
    configure_external_provider_api(monkeypatch)
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Provider pricing catalog is invalid."
    assert calls == []
    assert "not-json" not in response.text
    get_settings.cache_clear()


def test_external_provider_generate_api_requires_approval_before_transport(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello TOKEN=api-prompt-secret"}],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "External provider requires explicit approval."
    assert calls == []
    assert blocked_credentials.calls == []
    assert "external-api-key-secret" not in response.text
    assert "api-prompt-secret" not in response.text
    get_settings.cache_clear()


def test_external_provider_generate_api_requires_bound_approval_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
    blocked_credentials = BlockingCredentialEnviron()
    tracked_credentials = TrackingCredentialEnviron(
        key="DGENTIC_TEST_EXTERNAL_API_KEY",
        value="external-api-key-secret",
    )
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-provider-approval-api",
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Approved API response."},
                "finish_reason": "stop",
            }
        ],
        "token": "upstream-token-secret",
    }

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(raw_response).encode("utf-8")

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(
            {
                "url": request.full_url,
                "authorization": request.get_header("Authorization"),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return FakeResponse()

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_runtime, "environ", blocked_credentials)
    client = TestClient(create_app())
    provider_id = provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
    approval_body = {
        "provider_id": provider_id,
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "TOKEN=provider-api-prompt-secret"}],
        "temperature": 0.2,
        "max_tokens": 32,
        "agent_role": "developer",
        "task_id": "sprint-12",
    }

    bypass_response = client.post(
        "/providers/generate",
        json={**approval_body, "approved": True},
    )
    create_response = client.post(
        f"/providers/{provider_id}/approvals?requested_by=tester",
        json=approval_body,
    )
    approval_id = create_response.json()["id"]
    list_response = client.get("/providers/approvals?status=pending")
    review_response = client.get(f"/providers/approvals/{approval_id}/review")
    approve_response = client.post(
        f"/providers/approvals/{approval_id}/approve",
        json={"decided_by": "reviewer", "reason": "Approved with --token provider-reason-secret."},
    )
    mismatch_response = client.post(
        "/providers/generate",
        json={
            **approval_body,
            "messages": [{"role": "user", "content": "different"}],
            "approval_id": approval_id,
            "requested_by": "tester",
        },
    )
    monkeypatch.setattr(provider_runtime, "environ", tracked_credentials)
    execute_response = client.post(
        "/providers/generate",
        json={**approval_body, "approval_id": approval_id, "requested_by": "tester"},
    )
    second_execute_response = client.post(
        "/providers/generate",
        json={**approval_body, "approval_id": approval_id, "requested_by": "tester"},
    )
    logs_response = client.get("/logs?event_type=provider")

    assert bypass_response.status_code == 403
    assert "approval_id" in bypass_response.json()["detail"]
    assert create_response.status_code == 201
    assert create_response.json()["review_messages"] == [{"role": "user", "content_length": 32}]
    assert "provider-api-prompt-secret" not in create_response.text
    assert list_response.status_code == 200
    assert any(item["id"] == approval_id for item in list_response.json())
    assert review_response.status_code == 200
    assert review_response.json()["direct_execute_available"] is False
    assert "provider-api-prompt-secret" not in review_response.text
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"
    assert "--token [REDACTED]" in approve_response.json()["decision_reason"]
    assert "provider-reason-secret" not in approve_response.text
    assert mismatch_response.status_code == 403
    assert "not bound" in mismatch_response.json()["detail"]
    assert execute_response.status_code == 200
    assert execute_response.json()["content"] == "Approved API response."
    assert second_execute_response.status_code == 403
    assert "not executable" in second_execute_response.json()["detail"]
    assert calls == [
        {
            "url": "https://provider.example.test/v1/chat/completions",
            "authorization": "Bearer external-api-key-secret",
            "payload": {
                "model": "gpt-test",
                "messages": [{"role": "user", "content": "TOKEN=provider-api-prompt-secret"}],
                "stream": False,
                "temperature": 0.2,
                "max_tokens": 32,
            },
        }
    ]
    serialized = (
        create_response.text
        + list_response.text
        + review_response.text
        + approve_response.text
        + execute_response.text
        + logs_response.text
    )
    assert "external-api-key-secret" not in serialized
    assert "upstream-token-secret" not in serialized
    assert "provider-api-prompt-secret" not in serialized
    assert "Approved API response." in execute_response.text
    assert "Approved API response." not in logs_response.text
    assert blocked_credentials.calls == []
    assert tracked_credentials.calls == ["DGENTIC_TEST_EXTERNAL_API_KEY"]
    get_settings.cache_clear()


def test_provider_approval_approve_api_requires_approvals_capability(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "true")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        "provider-token=providers;approval-token=approvals",
    )
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch)
    get_settings.cache_clear()
    client = TestClient(create_app())
    provider_headers = {"Authorization": "Bearer provider-token"}
    approval_headers = {"Authorization": "Bearer approval-token"}
    provider_id = provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID

    provider_create_response = client.post(
        f"/providers/{provider_id}/approvals?requested_by=tester",
        headers=provider_headers,
        json={
            "provider_id": provider_id,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    create_response = client.post(
        f"/providers/{provider_id}/approvals?requested_by=tester",
        headers=approval_headers,
        json={
            "provider_id": provider_id,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    approval_id = create_response.json()["id"]
    provider_list_response = client.get("/providers/approvals", headers=provider_headers)
    approval_list_response = client.get("/providers/approvals", headers=approval_headers)
    provider_review_response = client.get(
        f"/providers/approvals/{approval_id}/review",
        headers=provider_headers,
    )
    provider_approve_response = client.post(
        f"/providers/approvals/{approval_id}/approve",
        headers=provider_headers,
        json={"decided_by": "spoofed-reviewer"},
    )
    provider_deny_response = client.post(
        f"/providers/approvals/{approval_id}/deny",
        headers=provider_headers,
        json={"decided_by": "spoofed-reviewer"},
    )
    approval_approve_response = client.post(
        f"/providers/approvals/{approval_id}/approve",
        headers=approval_headers,
        json={"decided_by": "spoofed-reviewer"},
    )

    assert provider_create_response.status_code == 403
    assert create_response.status_code == 201
    assert provider_list_response.status_code == 403
    assert approval_list_response.status_code == 200
    assert provider_review_response.status_code == 403
    assert provider_approve_response.status_code == 403
    assert provider_deny_response.status_code == 403
    assert approval_approve_response.status_code == 200
    assert (
        approval_approve_response.json()["decided_by"]
        == (sha256(b"approval-token").hexdigest()[:12])
    )
    get_settings.cache_clear()


def test_external_provider_generate_api_rejects_plain_http_config_before_transport(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    configure_external_provider_api(monkeypatch, base_url="http://provider.example.test/v1")
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )

    assert response.status_code == 403
    assert "https" in response.json()["detail"]
    assert calls == []
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_external_provider_generate_api_missing_config_fails_before_transport(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", "")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "DGENTIC_TEST_EXTERNAL")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    monkeypatch.setenv("DGENTIC_TEST_EXTERNAL", "external-api-key-secret")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "External provider is not configured."
    assert calls == []
    assert "external-api-key-secret" not in response.text
    get_settings.cache_clear()


def test_external_provider_generate_api_rejects_runtime_base_url_before_transport(
    monkeypatch,
) -> None:
    configure_external_provider_api(monkeypatch)
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-test",
            "base_url": "https://evil.example.test/v1",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 403
    assert calls == []
    get_settings.cache_clear()


def test_external_provider_generate_api_rejects_model_outside_allowlist_before_transport(
    monkeypatch,
) -> None:
    configure_external_provider_api(monkeypatch, models="gpt-test")
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise AssertionError("transport should not be called")

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            "model": "gpt-not-allowed",
            "messages": [{"role": "user", "content": "hello"}],
            "approved": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "External provider model is not configured."
    assert calls == []
    get_settings.cache_clear()


def test_provider_generate_api_maps_exhausted_429_to_too_many_requests(monkeypatch) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            {"Retry-After": "1"},
            BytesIO(b'{"token":"rate-limit-secret"}'),
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=2),
    )
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Provider request failed."
    assert len(calls) == 2
    assert sleeps == [1.0]
    assert "rate-limit-secret" not in response.text


def test_provider_generate_api_maps_exhausted_5xx_to_bad_gateway(monkeypatch) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise HTTPError(
            request.full_url,
            503,
            "Unavailable",
            {},
            BytesIO(b'{"token":"server-error-secret"}'),
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=2),
    )
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    assert len(calls) == 2
    assert sleeps == [0.2]
    assert "server-error-secret" not in response.text


def test_provider_generate_api_maps_open_circuit_to_503_without_transport(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("DGENTIC_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()
    calls: list[str] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise HTTPError(
            request.full_url,
            503,
            "Provider unavailable.",
            {},
            BytesIO(b'{"token":"upstream-error-secret"}'),
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(
        provider_runtime,
        "_generation_retry_policy",
        lambda: provider_transport.ProviderRetryPolicy(max_attempts=1),
    )
    client = TestClient(create_app())
    payload = {
        "provider_id": "lm-studio",
        "model": "local-model",
        "base_url": "http://127.0.0.1:1234",
        "messages": [{"role": "user", "content": "hello"}],
    }

    first_response = client.post("/providers/generate", json=payload)
    second_response = client.post("/providers/generate", json=payload)

    assert first_response.status_code == 502
    assert second_response.status_code == 503
    assert second_response.json()["detail"] == "Provider circuit is open."
    assert len(calls) == 1
    assert "upstream-error-secret" not in first_response.text + second_response.text
    get_settings.cache_clear()


@pytest.mark.parametrize("status_code", [401, 408])
def test_provider_generate_api_maps_provider_4xx_without_retry(status_code, monkeypatch) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_open_provider_request(request, *, timeout_seconds: float):
        calls.append(request.full_url)
        raise HTTPError(
            request.full_url,
            status_code,
            "Provider client error.",
            {"Authorization": "Bearer upstream-auth-secret"},
            BytesIO(b'{"token":"auth-error-secret"}'),
        )

    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    assert len(calls) == 1
    assert sleeps == []
    assert "upstream-auth-secret" not in response.text
    assert "auth-error-secret" not in response.text


def test_provider_generate_api_maps_malformed_upstream_json_to_bad_gateway(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"not": "valid"'

    def fake_open_provider_request(request, *, timeout_seconds: float) -> FakeResponse:
        return FakeResponse()

    sleeps: list[float] = []
    monkeypatch.setattr(provider_transport, "open_provider_request", fake_open_provider_request)
    monkeypatch.setattr(provider_transport, "sleep_provider_retry", sleeps.append)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    assert sleeps == []


def test_provider_generate_api_maps_malformed_success_payload_to_bad_gateway(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append(url)
        return {"error": {"message": "upstream-provider-secret"}}

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Provider request failed."
    assert calls == ["http://127.0.0.1:1234/v1/chat/completions"]
    assert "upstream-provider-secret" not in response.text


def test_provider_generate_api_returns_safe_metadata_and_logs(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    get_settings.cache_clear()
    raw_secrets = [
        "upstream-response-token-secret",
        "upstream-response-authorization-secret",
    ]
    calls: list[dict] = []
    raw_response = {
        "id": "chatcmpl-safe-api-upstream-secret",
        "model": "local-model-upstream-secret",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from provider API."},
                "finish_reason": "unsafe-upstream-finish-secret",
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
            "load_duration": -1,
            "eval_count": 10**309,
            "prompt": "usage-prompt-secret",
            "total": "usage-total-secret",
        },
        "token": raw_secrets[0],
        "authorization": f"Bearer {raw_secrets[1]}",
    }

    def fake_post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return raw_response

    monkeypatch.setattr(provider_runtime, "_post_json", fake_post_json)
    client = TestClient(create_app())

    response = client.post(
        "/providers/generate",
        json={
            "provider_id": "lm-studio",
            "model": "local-model",
            "base_url": "http://127.0.0.1:1234",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
            "max_tokens": 32,
        },
    )
    logs_response = client.get("/logs?event_type=provider")

    assert response.status_code == 200
    assert calls == [
        {
            "url": "http://127.0.0.1:1234/v1/chat/completions",
            "payload": {
                "model": "local-model",
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.2,
                "max_tokens": 32,
                "stream": False,
            },
            "timeout_seconds": 60.0,
        }
    ]
    body = response.json()
    assert body["content"] == "Hello from provider API."
    assert body["usage_metadata"] == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }
    assert body["estimated_cost_usd"] == 0.0
    assert body["raw_response_metadata"] == {
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        "choice_count": 1,
        "finish_reasons": ["other"],
    }
    serialized_response = response.text
    metadata_secrets = [
        "chatcmpl-safe-api-upstream-secret",
        "local-model-upstream-secret",
        "unsafe-upstream-finish-secret",
        "usage-prompt-secret",
        "usage-total-secret",
    ]
    for raw_secret in raw_secrets + metadata_secrets:
        assert raw_secret not in serialized_response

    assert logs_response.status_code == 200
    provider_events = logs_response.json()
    assert provider_events[-1]["message"] == "Completed provider generation."
    assert "content" not in provider_events[-1]["metadata"]
    assert provider_events[-1]["metadata"]["usage_metadata"] == body["usage_metadata"]
    assert provider_events[-1]["metadata"]["estimated_cost_usd"] == 0.0
    serialized_logs = json.dumps(provider_events, sort_keys=True)
    assert "Hello from provider API." not in serialized_logs
    for raw_secret in raw_secrets + metadata_secrets:
        assert raw_secret not in serialized_logs
    get_settings.cache_clear()


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


def _poll_api_execution(
    client: TestClient,
    run_id: str,
    execution_id: str,
    *,
    headers: dict[str, str] | None = None,
    attempts: int = 50,
) -> dict:
    for _ in range(attempts):
        response = client.get(
            f"/tasks/orchestrations/{run_id}/executions/{execution_id}",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        if body["status"] not in {"starting", "running"}:
            return body
        time.sleep(0.01)
    pytest.fail(f"Background execution did not finish: {execution_id}")


def _interface_signature(interface: dict) -> str:
    payload = json.dumps(interface, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"
