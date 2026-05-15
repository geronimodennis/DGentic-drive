import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from dgentic.auth import capability_for_path
from dgentic.command_recipes import (
    CommandRecipeExecutionRequest,
    CommandRecipeParameter,
    CommandRecipeRequest,
    CommandRecipeUpdate,
    PluginCommandRecipeInstallRequest,
    build_command_recipe_request,
    create_command_recipe,
    expand_command_recipe,
    get_command_recipe,
    install_plugin_command_recipe,
    list_command_recipes,
    record_command_recipe_usage,
    update_command_recipe,
)
from dgentic.events import event_log
from dgentic.main import create_app
from dgentic.schemas import LogEventType
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


def _enable_managed_command_recipes(tmp_path, monkeypatch, recipes: list[dict]) -> None:
    managed_path = tmp_path / "managed-settings.json"
    managed_path.write_text(
        json.dumps({"settings": {"managed_command_recipes": recipes}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", str(managed_path))
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


def test_managed_recipes_overlay_local_records_without_persisting(
    recipe_state,
    tmp_path,
    monkeypatch,
) -> None:
    _root_dir, data_dir = recipe_state
    create_command_recipe(
        CommandRecipeRequest(
            id="shared.echo",
            name="Local shared echo",
            command_template="cmd /c echo local",
        )
    )
    create_command_recipe(
        CommandRecipeRequest(
            id="local.echo",
            name="Local echo",
            command_template="cmd /c echo local-only",
        )
    )

    _enable_managed_command_recipes(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "shared.echo",
                "name": "Managed shared echo",
                "command_template": "cmd /c echo managed",
                "tags": ["managed"],
            },
            {
                "id": "managed.echo",
                "name": "Managed echo",
                "command_template": "cmd /c echo managed-only",
            },
        ],
    )

    recipes = list_command_recipes()
    shared = get_command_recipe("shared.echo")
    state_text = (data_dir / "command-recipes.json").read_text(encoding="utf-8")

    assert [(recipe.id, recipe.source) for recipe in recipes] == [
        ("managed.echo", "managed"),
        ("shared.echo", "managed"),
        ("local.echo", "local"),
    ]
    assert shared.name == "Managed shared echo"
    assert shared.source == "managed"
    assert "Local shared echo" in state_text
    assert "Managed shared echo" not in state_text


def test_managed_recipes_are_read_only_and_block_local_or_plugin_shadowing(
    recipe_state,
    tmp_path,
    monkeypatch,
) -> None:
    _root_dir, data_dir = recipe_state
    _enable_managed_command_recipes(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "managed.deploy",
                "name": "Managed deploy",
                "command_template": "cmd /c echo deploy",
            }
        ],
    )

    with pytest.raises(ValueError, match="already exists"):
        create_command_recipe(
            CommandRecipeRequest(
                id="managed.deploy",
                name="Local deploy",
                command_template="cmd /c echo local",
            )
        )
    with pytest.raises(PermissionError, match="Managed command recipes cannot be modified"):
        update_command_recipe(
            "managed.deploy",
            CommandRecipeUpdate(description="Attempted local override."),
        )
    with pytest.raises(ValueError, match="already in use"):
        install_plugin_command_recipe(
            PluginCommandRecipeInstallRequest(
                recipe=CommandRecipeRequest(
                    id="managed.deploy",
                    name="Plugin deploy",
                    command_template="cmd /c echo plugin",
                ),
                plugin_id="deploy-plugin",
                manifest_digest="a" * 64,
                component_path="recipes/deploy.json",
                component_digest="b" * 64,
            )
        )

    assert not (data_dir / "command-recipes.json").exists()


def test_managed_recipe_usage_audits_without_mutating_local_state(
    recipe_state,
    tmp_path,
    monkeypatch,
) -> None:
    _root_dir, data_dir = recipe_state
    _enable_managed_command_recipes(
        tmp_path,
        monkeypatch,
        [
            {
                "id": "managed.usage",
                "name": "Managed usage",
                "command_template": "cmd /c echo usage",
            }
        ],
    )

    used = record_command_recipe_usage("managed.usage", action="execute", actor="qa")
    latest_event = event_log.list(LogEventType.cli)[-1]

    assert used.id == "managed.usage"
    assert used.source == "managed"
    assert used.usage_count == 0
    assert latest_event.message == "Used command recipe."
    assert latest_event.actor == "qa"
    assert latest_event.metadata["recipe_id"] == "managed.usage"
    assert latest_event.metadata["source"] == "managed"
    assert latest_event.metadata["action"] == "execute"
    assert not (data_dir / "command-recipes.json").exists()


def test_locally_persisted_managed_source_rows_do_not_spoof_managed_settings(
    recipe_state,
) -> None:
    _root_dir, data_dir = recipe_state
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "command-recipes.json").write_text(
        json.dumps(
            [
                {
                    "id": "spoofed.managed",
                    "name": "Spoofed managed",
                    "command_template": "cmd /c echo spoofed",
                    "source": "managed",
                }
            ]
        ),
        encoding="utf-8",
    )

    assert list_command_recipes() == []
    with pytest.raises(KeyError, match="Command recipe not found"):
        get_command_recipe("spoofed.managed")
    with pytest.raises(PermissionError, match="Managed command recipes must come from"):
        record_command_recipe_usage("spoofed.managed", action="execute", actor="qa")
    with pytest.raises(PermissionError, match="Managed command recipes cannot be modified"):
        update_command_recipe(
            "spoofed.managed",
            CommandRecipeUpdate(description="Attempted spoof mutation."),
        )


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


def test_recipe_api_patch_toggles_local_recipe_execution(recipe_state) -> None:
    root_dir, _data_dir = recipe_state
    client = TestClient(create_app())

    create_response = client.post(
        "/cli/recipes",
        json={
            "id": "qa.echo",
            "name": "QA echo",
            "command_template": "cmd /c echo {{message}}",
            "cwd": str(root_dir),
            "parameters": [{"name": "message"}],
        },
    )
    patch_response = client.patch(
        "/cli/recipes/qa.echo",
        json={"name": "QA echo edited", "enabled": False},
    )
    disabled_preview = client.post(
        "/cli/recipes/qa.echo/preview",
        json={"parameters": {"message": "hello"}},
    )
    reenable_response = client.patch("/cli/recipes/qa.echo", json={"enabled": True})

    assert create_response.status_code == 201
    assert patch_response.status_code == 200
    assert patch_response.json()["source"] == "local"
    assert patch_response.json()["enabled"] is False
    assert patch_response.json()["name"] == "QA echo edited"
    assert disabled_preview.status_code == 403
    assert "disabled" in disabled_preview.text
    assert reenable_response.status_code == 200
    assert reenable_response.json()["enabled"] is True


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
