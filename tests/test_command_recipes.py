import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from dgentic.auth import capability_for_path
from dgentic.command_recipes import (
    CommandRecipeExecutionRequest,
    CommandRecipeParameter,
    CommandRecipeRequest,
    build_command_recipe_request,
    create_command_recipe,
    expand_command_recipe,
    get_command_recipe,
    list_command_recipes,
)
from dgentic.main import create_app
from dgentic.settings import get_settings


@pytest.fixture(autouse=True)
def recipe_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DGENTIC_APPROVAL_DIGEST_KEY", "recipe-test-key")
    get_settings.cache_clear()
    yield root_dir, data_dir
    get_settings.cache_clear()


def test_recipe_registry_persists_redacts_and_lists_safe_contract(recipe_state) -> None:
    _root_dir, data_dir = recipe_state

    recipe = create_command_recipe(
        CommandRecipeRequest(
            id="qa.echo",
            name="QA echo",
            description="Echo a safe value.",
            command_template="cmd /c echo {{message}}",
            parameters=[
                CommandRecipeParameter(
                    name="message",
                    description="Safe message",
                )
            ],
            tags=["qa", "smoke"],
        ),
        actor="qa",
    )

    state_text = (data_dir / "command-recipes.json").read_text(encoding="utf-8")
    state = json.loads(state_text)
    assert recipe.id == "qa.echo"
    assert get_command_recipe("qa.echo").name == "QA echo"
    assert [item.id for item in list_command_recipes()] == ["qa.echo"]
    assert state[0]["command_template"] == "cmd /c echo {{message}}"
    assert "secret" not in state_text.lower()


def test_recipe_rejects_secret_shaped_templates_and_injection_parameters() -> None:
    with pytest.raises(ValueError, match="secret-shaped"):
        create_command_recipe(
            CommandRecipeRequest(
                id="bad.secret",
                name="bad secret",
                command_template="cmd /c echo --token {{token}}",
                parameters=[CommandRecipeParameter(name="token")],
            )
        )

    recipe = create_command_recipe(
        CommandRecipeRequest(
            id="qa.echo",
            name="QA echo",
            command_template="cmd /c echo {{message}}",
            parameters=[CommandRecipeParameter(name="message")],
        )
    )

    with pytest.raises(ValueError, match="parameter values"):
        build_command_recipe_request(
            recipe.id,
            CommandRecipeExecutionRequest(parameters={"message": "ok; rm -rf important"}),
        )


def test_recipe_expansion_uses_command_policy_after_parameter_binding() -> None:
    recipe = create_command_recipe(
        CommandRecipeRequest(
            id="git.status",
            name="Git status",
            command_template="git status --short {{path}}",
            parameters=[CommandRecipeParameter(name="path", default=".")],
        )
    )

    expansion = expand_command_recipe(
        recipe.id,
        CommandRecipeExecutionRequest(parameters={"path": "."}, requested_by="pm"),
    )

    assert expansion.command == "git status --short ."
    assert expansion.policy.permission_mode == "approval_required"
    assert expansion.parameter_names == ["path"]
    assert expansion.requested_by == "pm"


def test_recipe_api_expands_and_runs_safe_recipe_with_authenticated_principal(
    recipe_state,
    monkeypatch,
) -> None:
    root_dir, _data_dir = recipe_state
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "cli-token=cli;admin-token=admin")
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/recipes",
        headers={"Authorization": "Bearer cli-token"},
        json={
            "id": "qa.echo",
            "name": "QA echo",
            "command_template": "cmd /c echo {{message}}",
            "cwd": str(root_dir),
            "parameters": [{"name": "message"}],
        },
    )
    preview_response = client.post(
        "/cli/recipes/qa.echo/preview",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"message": "hello"}, "requested_by": "spoofed"},
    )
    execute_response = client.post(
        "/cli/recipes/qa.echo/execute",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"message": "hello"}, "requested_by": "spoofed"},
    )
    run_response = client.post(
        "/cli/recipes/qa.echo/runs",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"message": "hello"}, "requested_by": "spoofed"},
    )

    assert create_response.status_code == 201
    assert preview_response.status_code == 200
    assert preview_response.json()["command"] == "cmd /c echo hello"
    assert preview_response.json()["requested_by"] == sha256(b"cli-token").hexdigest()[:12]
    assert execute_response.status_code == 200
    assert execute_response.json()["command"] == "cmd /c echo hello"
    assert execute_response.json()["requested_by"] == sha256(b"cli-token").hexdigest()[:12]
    assert "hello" in execute_response.json()["stdout"]
    assert run_response.status_code == 202
    assert run_response.json()["command"] == "cmd /c echo hello"
    assert run_response.json()["requested_by"] == sha256(b"cli-token").hexdigest()[:12]


def test_recipe_api_requires_bound_approval_for_approval_required_command_in_production(
    recipe_state,
    monkeypatch,
) -> None:
    root_dir, _data_dir = recipe_state
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DGENTIC_AUTH_TOKENS",
        "cli-token=cli;approval-token=approvals;admin-token=admin",
    )
    get_settings.cache_clear()
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/recipes",
        headers={"Authorization": "Bearer cli-token"},
        json={
            "id": "git.status",
            "name": "Git status",
            "command_template": "git status --short {{path}}",
            "cwd": str(root_dir),
            "parameters": [{"name": "path", "default": "."}],
        },
    )
    boolean_bypass_response = client.post(
        "/cli/recipes/git.status/runs",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"path": "."}, "approved": True},
    )
    approval_response = client.post(
        "/cli/recipes/git.status/approvals",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"path": "."}},
    )
    approval_id = approval_response.json()["id"]
    approve_response = client.post(
        f"/cli/approvals/{approval_id}/approve",
        headers={"Authorization": "Bearer approval-token"},
        json={"reason": "Safe git status."},
    )
    run_response = client.post(
        "/cli/recipes/git.status/runs",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"path": "."}, "approval_id": approval_id},
    )
    replay_response = client.post(
        "/cli/recipes/git.status/runs",
        headers={"Authorization": "Bearer cli-token"},
        json={"parameters": {"path": "."}, "approval_id": approval_id},
    )

    assert create_response.status_code == 201
    assert boolean_bypass_response.status_code == 422
    assert approval_response.status_code == 201
    assert approval_response.json()["review_command"] == "git status --short ."
    assert approve_response.status_code == 200
    assert run_response.status_code == 202
    assert run_response.json()["approval_id"] == approval_id
    assert replay_response.status_code == 403


def test_recipe_routes_use_cli_capability() -> None:
    assert capability_for_path("/cli/recipes") == "cli"
    assert capability_for_path("/cli/recipes/qa.echo/execute") == "cli"
    assert capability_for_path("/cli/recipes/qa.echo/runs") == "cli"
    assert capability_for_path("/cli/recipes/qa.echo/approvals") == "cli"
