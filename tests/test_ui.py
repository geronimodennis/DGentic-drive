from fastapi.testclient import TestClient

from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.settings import get_settings


def test_web_ui_entrypoint_is_served() -> None:
    client = TestClient(create_app())

    response = client.get("/ui/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "DGentic Control" in response.text
    assert "Workspace" in response.text
    assert "Project" in response.text
    assert "Context" in response.text
    assert "Active root" in response.text
    assert "CLI Runs" in response.text
    assert "Rules And Plugins" in response.text
    assert "./app.js" in response.text
    assert "./app.css" in response.text


def test_web_ui_static_assets_are_served() -> None:
    client = TestClient(create_app())

    script_response = client.get("/ui/app.js")
    style_response = client.get("/ui/app.css")

    assert script_response.status_code == 200
    assert "const TOKEN_KEY" in script_response.text
    assert "approvalSources" in script_response.text
    assert "headers.Authorization" in script_response.text
    assert 'api("/filesystem/list"' in script_response.text
    assert 'api("/filesystem/read"' in script_response.text
    assert 'api("/filesystem/write"' in script_response.text
    assert 'api("/cli/runs"' in script_response.text
    assert "api(`/cli/runs/${encodeURIComponent(runId)}/output`)" in script_response.text
    assert "api(`/cli/approvals/${encodeURIComponent(approvalId)}/execute`" in script_response.text
    assert 'api("/cli/policy/rules")' in script_response.text
    assert 'api("/cli/recipes")' in script_response.text
    assert 'api("/guardrails/hooks/rules")' in script_response.text
    assert 'api("/plugins")' in script_response.text
    assert 'api("/settings/effective")' in script_response.text
    assert "renderProjectContext" in script_response.text
    assert "activeRootDir" in script_response.text
    assert "projectOpenRootButton" in script_response.text
    assert "projectPreflightButton" in script_response.text
    assert "projectForm" in script_response.text
    assert 'api("/projects/preflight"' in script_response.text
    assert 'api("/projects"' in script_response.text
    assert 'api("/projects/active")' in script_response.text
    assert "activateProject" in script_response.text
    assert "api(`/projects/${encodeURIComponent(projectId)}/activate`" in script_response.text
    assert "renderActivationChecks" in script_response.text
    assert "workspaceRootButton" in script_response.text
    assert "renderGitCheckpoint" in script_response.text
    assert "checkpoint-grid" in script_response.text
    assert style_response.status_code == 200
    assert ".app-shell" in style_response.text
    assert ".workspace-layout" in style_response.text
    assert ".context-grid" in style_response.text
    assert ".checkpoint-grid" in style_response.text
    assert ".policy-grid" in style_response.text
    assert ".approval-list" in style_response.text


def test_web_ui_is_public_while_api_routes_remain_protected(tmp_path, monkeypatch) -> None:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "admin-token=admin")
    get_settings.cache_clear()
    reset_database_state()

    client = TestClient(create_app())

    ui_response = client.get("/ui/")
    api_response = client.get("/tasks/plans")

    assert ui_response.status_code == 200
    assert "DGentic Control" in ui_response.text
    assert api_response.status_code == 401

    reset_database_state()
    get_settings.cache_clear()
