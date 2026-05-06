from fastapi.testclient import TestClient

from dgentic.main import create_app


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
