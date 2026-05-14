from datetime import UTC, datetime

from fastapi.testclient import TestClient

from dgentic.cli_runtime import CommandApproval, CommandRun, CommandRunStatus, cli_runtime_service
from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.orchestration import orchestration_service
from dgentic.schemas import OrchestrationRun, OrchestrationTask, PermissionMode, StepStatus
from dgentic.settings import clear_runtime_settings_overrides, get_settings


def _configure_project_state(tmp_path, monkeypatch):
    clear_runtime_settings_overrides()
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(state_dir))
    get_settings.cache_clear()
    reset_database_state()
    return root_dir, state_dir


def _reset_project_state() -> None:
    reset_database_state()
    clear_runtime_settings_overrides()
    get_settings.cache_clear()


def test_project_preflight_validates_candidate_roots(tmp_path, monkeypatch) -> None:
    root_dir, state_dir = _configure_project_state(tmp_path, monkeypatch)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "pyproject.toml").write_text("[project]\nname='candidate'\n", encoding="utf-8")
    (candidate / ".git").mkdir()
    file_candidate = tmp_path / "not-a-directory.txt"
    file_candidate.write_text("nope", encoding="utf-8")

    client = TestClient(create_app())

    valid_response = client.post(
        "/projects/preflight",
        json={"root_dir": str(candidate), "name": "TOKEN=project-secret"},
    )
    missing_response = client.post(
        "/projects/preflight",
        json={"root_dir": str(tmp_path / "missing")},
    )
    file_response = client.post(
        "/projects/preflight",
        json={"root_dir": str(file_candidate)},
    )
    relative_response = client.post(
        "/projects/preflight",
        json={"root_dir": "relative-project"},
    )
    state_response = client.post(
        "/projects/preflight",
        json={"root_dir": str(state_dir)},
    )

    assert valid_response.status_code == 200
    assert valid_response.json()["root_dir"] == str(candidate.resolve())
    assert valid_response.json()["markers"] == [".git", "pyproject.toml"]
    assert "project-secret" not in valid_response.text
    assert valid_response.json()["warnings"] == [
        "Registering a project does not change the active runtime root."
    ]
    assert missing_response.status_code == 400
    assert file_response.status_code == 400
    assert relative_response.status_code == 400
    assert state_response.status_code == 400

    _reset_project_state()


def test_project_registry_persists_without_switching_active_root(tmp_path, monkeypatch) -> None:
    root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    (root_dir / "original.txt").write_text("active root", encoding="utf-8")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "candidate-only.txt").write_text("candidate root", encoding="utf-8")

    client = TestClient(create_app())

    create_response = client.post(
        "/projects",
        json={"id": "candidate-project", "name": "Candidate", "root_dir": str(candidate)},
    )
    duplicate_response = client.post(
        "/projects",
        json={"id": "candidate-duplicate", "name": "Duplicate", "root_dir": str(candidate)},
    )
    list_response = client.get("/projects")
    detail_response = client.get("/projects/candidate-project")
    update_response = client.patch(
        "/projects/candidate-project",
        json={"name": "Candidate archived", "status": "archived"},
    )
    restarted_client = TestClient(create_app())
    restarted_list_response = restarted_client.get("/projects")
    settings_response = restarted_client.get("/settings/effective")
    filesystem_response = restarted_client.post("/filesystem/list", json={"path": "."})

    assert create_response.status_code == 201
    assert create_response.json()["id"] == "candidate-project"
    assert create_response.json()["root_dir"] == str(candidate.resolve())
    assert create_response.json()["last_opened_at"] is None
    assert duplicate_response.status_code == 409
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == ["candidate-project"]
    assert detail_response.status_code == 200
    assert detail_response.json()["name"] == "Candidate"
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "archived"
    assert restarted_list_response.status_code == 200
    assert restarted_list_response.json()[0]["name"] == "Candidate archived"
    root_setting = next(
        item for item in settings_response.json()["settings"] if item["name"] == "root_dir"
    )
    assert root_setting["value"] == str(root_dir)
    listed_names = {item["name"] for item in filesystem_response.json()["entries"]}
    assert "original.txt" in listed_names
    assert "candidate-only.txt" not in listed_names

    _reset_project_state()


def test_active_project_reports_registered_current_root(tmp_path, monkeypatch) -> None:
    root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    client = TestClient(create_app())

    before_response = client.get("/projects/active")
    create_response = client.post(
        "/projects",
        json={"id": "active-root", "name": "Active root", "root_dir": str(root_dir)},
    )
    after_response = client.get("/projects/active")

    assert before_response.status_code == 200
    assert before_response.json()["active_root_dir"] == str(root_dir)
    assert before_response.json()["project"] is None
    assert before_response.json()["switching_available"] is True
    assert create_response.status_code == 201
    assert create_response.json()["last_opened_at"] is not None
    assert after_response.status_code == 200
    assert after_response.json()["project"]["id"] == "active-root"
    assert after_response.json()["switching_available"] is True

    _reset_project_state()


def test_project_activation_switches_runtime_root_and_preserves_state(
    tmp_path,
    monkeypatch,
) -> None:
    root_dir, state_dir = _configure_project_state(tmp_path, monkeypatch)
    root_dir.joinpath("old-only.txt").write_text("old root", encoding="utf-8")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    candidate.joinpath("candidate-only.txt").write_text("new root", encoding="utf-8")

    client = TestClient(create_app())
    create_response = client.post(
        "/projects",
        json={"id": "candidate-project", "name": "Candidate", "root_dir": str(candidate)},
    )
    preflight_response = client.post("/projects/candidate-project/activation/preflight")
    activate_response = client.post("/projects/candidate-project/activate")
    active_response = client.get("/projects/active")
    settings_response = client.get("/settings/effective")
    filesystem_response = client.post("/filesystem/list", json={"path": "."})
    list_response = client.get("/projects")

    assert create_response.status_code == 201
    assert preflight_response.status_code == 200
    assert preflight_response.json()["can_activate"] is True
    assert any(check["id"] == "state-anchor" for check in preflight_response.json()["checks"])
    assert activate_response.status_code == 200
    assert activate_response.json()["switched"] is True
    assert activate_response.json()["previous_root_dir"] == str(root_dir)
    assert activate_response.json()["active_root_dir"] == str(candidate.resolve())
    assert active_response.status_code == 200
    assert active_response.json()["project"]["id"] == "candidate-project"
    root_setting = next(
        item for item in settings_response.json()["settings"] if item["name"] == "root_dir"
    )
    data_setting = next(
        item for item in settings_response.json()["settings"] if item["name"] == "data_dir"
    )
    assert root_setting["value"] == str(candidate.resolve())
    assert root_setting["source"] == "runtime"
    assert data_setting["value"] == str(state_dir.resolve())
    assert data_setting["source"] == "runtime"
    listed_names = {item["name"] for item in filesystem_response.json()["entries"]}
    assert "candidate-only.txt" in listed_names
    assert "old-only.txt" not in listed_names
    assert list_response.status_code == 200
    assert list_response.json()[0]["last_opened_at"] is not None

    _reset_project_state()


def test_project_activation_blocks_unexecuted_approvals(tmp_path, monkeypatch) -> None:
    root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    cli_runtime_service._approvals.upsert(
        CommandApproval(
            id="approval-root-switch",
            command="echo approved",
            cwd=root_dir,
            timeout_seconds=30,
            policy_reason="approval required",
        )
    )
    client = TestClient(create_app())
    client.post(
        "/projects",
        json={"id": "candidate-project", "name": "Candidate", "root_dir": str(candidate)},
    )

    preflight_response = client.post("/projects/candidate-project/activation/preflight")
    activate_response = client.post("/projects/candidate-project/activate")
    settings_response = client.get("/settings/effective")

    assert preflight_response.status_code == 200
    assert preflight_response.json()["can_activate"] is False
    assert "cli: 1" in " ".join(preflight_response.json()["blockers"])
    assert activate_response.status_code == 409
    assert activate_response.json()["detail"]["can_activate"] is False
    root_setting = next(
        item for item in settings_response.json()["settings"] if item["name"] == "root_dir"
    )
    assert root_setting["value"] == str(root_dir)

    _reset_project_state()


def test_project_activation_blocks_active_cli_runs(tmp_path, monkeypatch) -> None:
    root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    cli_runtime_service._runs.upsert(
        CommandRun(
            id="run-root-switch",
            command="python -m http.server",
            cwd=root_dir,
            status=CommandRunStatus.running,
            permission_mode=PermissionMode.autopilot_safe,
            duration_ms=0,
            started_at=datetime.now(UTC),
        )
    )
    client = TestClient(create_app())
    client.post(
        "/projects",
        json={"id": "candidate-project", "name": "Candidate", "root_dir": str(candidate)},
    )

    activate_response = client.post("/projects/candidate-project/activate")

    assert activate_response.status_code == 409
    assert "Active CLI runs" in " ".join(activate_response.json()["detail"]["blockers"])

    _reset_project_state()


def test_project_activation_blocks_running_orchestration_tasks(tmp_path, monkeypatch) -> None:
    _root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    orchestration_service._runs.upsert(
        OrchestrationRun(
            id="run-root-switch",
            objective="root switch guard",
            tasks=[
                OrchestrationTask(
                    id="task-root-switch",
                    title="Running work",
                    description="Root-bound work",
                    role="developer",
                    status=StepStatus.running,
                    agent_id="agent-root-switch",
                )
            ],
        )
    )
    client = TestClient(create_app())
    client.post(
        "/projects",
        json={"id": "candidate-project", "name": "Candidate", "root_dir": str(candidate)},
    )

    activate_response = client.post("/projects/candidate-project/activate")

    assert activate_response.status_code == 409
    assert "Running orchestration tasks" in " ".join(activate_response.json()["detail"]["blockers"])

    _reset_project_state()


def test_project_activation_rejects_archived_or_invalid_roots(tmp_path, monkeypatch) -> None:
    root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    deleted = tmp_path / "deleted"
    deleted.mkdir()
    client = TestClient(create_app())
    client.post(
        "/projects",
        json={"id": "archived-project", "name": "Archived", "root_dir": str(candidate)},
    )
    client.patch("/projects/archived-project", json={"status": "archived"})
    client.post(
        "/projects",
        json={"id": "deleted-project", "name": "Deleted", "root_dir": str(deleted)},
    )
    deleted.rmdir()

    missing_response = client.post("/projects/missing/activate")
    archived_response = client.post("/projects/archived-project/activate")
    deleted_response = client.post("/projects/deleted-project/activate")

    assert missing_response.status_code == 404
    assert archived_response.status_code == 409
    assert "archived" in " ".join(archived_response.json()["detail"]["blockers"])
    assert deleted_response.status_code == 400
    assert root_dir == get_settings().root_dir

    _reset_project_state()


def test_project_routes_require_admin_capability(tmp_path, monkeypatch) -> None:
    root_dir, _state_dir = _configure_project_state(tmp_path, monkeypatch)
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "admin-token=admin;task-token=tasks")
    get_settings.cache_clear()

    client = TestClient(create_app())

    unauthenticated_response = client.get("/projects")
    task_response = client.get("/projects", headers={"Authorization": "Bearer task-token"})
    admin_response = client.post(
        "/projects/preflight",
        headers={"Authorization": "Bearer admin-token"},
        json={"root_dir": str(root_dir)},
    )

    assert unauthenticated_response.status_code == 401
    assert task_response.status_code == 403
    assert admin_response.status_code == 200

    _reset_project_state()
