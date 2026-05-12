import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from dgentic.auth import (
    AuthConfigurationError,
    capability_for_path,
    capability_for_request,
    parse_token_map,
    validate_auth_configuration,
)
from dgentic.credentials import credential_env_for_reference, credential_secret_for_reference
from dgentic.events import event_log
from dgentic.main import create_app
from dgentic.schemas import LogEventType
from dgentic.settings import Settings, get_settings

TASK_REQUEST = {"objective": "Verify production auth baseline."}
TOKEN_CONFIG = "task-token=tasks;admin-token=admin;fs-token=filesystem"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def client_with_auth_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str,
    auth_tokens: str = TOKEN_CONFIG,
    auth_enabled: str | None = None,
) -> TestClient:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", environment)
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", auth_tokens)
    if auth_enabled is None:
        monkeypatch.delenv("DGENTIC_AUTH_ENABLED", raising=False)
    else:
        monkeypatch.setenv("DGENTIC_AUTH_ENABLED", auth_enabled)
    get_settings.cache_clear()
    return TestClient(create_app())


def production_client_with_state(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    auth_tokens: str = "bootstrap-token=admin",
) -> TestClient:
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", auth_tokens)
    get_settings.cache_clear()
    return TestClient(create_app())


def create_operator(
    client: TestClient,
    operator_id: str,
    capabilities: list[str],
    *,
    auth_token: str = "bootstrap-token",
    display_name: str = "",
    role: str = "",
    group_ids: list[str] | None = None,
) -> dict:
    response = client.post(
        "/auth/operators",
        headers=bearer(auth_token),
        json={
            "operator_id": operator_id,
            "display_name": display_name,
            "role": role,
            "capabilities": capabilities,
            "group_ids": group_ids or [],
        },
    )
    assert response.status_code == 201
    return response.json()


def create_operator_group(
    client: TestClient,
    group_id: str,
    capabilities: list[str],
    *,
    auth_token: str = "bootstrap-token",
    display_name: str = "",
    description: str = "",
) -> dict:
    response = client.post(
        "/auth/operator-groups",
        headers=bearer(auth_token),
        json={
            "group_id": group_id,
            "display_name": display_name,
            "description": description,
            "capabilities": capabilities,
        },
    )
    assert response.status_code == 201
    return response.json()


def issue_auth_token(
    client: TestClient,
    operator_id: str,
    capabilities: list[str],
    *,
    auth_token: str = "bootstrap-token",
    label: str = "",
    expires_at: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "operator_id": operator_id,
        "capabilities": capabilities,
    }
    if label:
        payload["label"] = label
    if expires_at is not None:
        payload["expires_at"] = expires_at
    response = client.post(
        "/auth/tokens",
        headers=bearer(auth_token),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_development_default_auth_off_allows_task_plan_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_with_auth_env(monkeypatch, environment="development")

    response = client.post("/tasks/plan", json=TASK_REQUEST)

    assert response.status_code == 201


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_production_and_staging_default_auth_on_reject_task_plan_without_token(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    client = client_with_auth_env(monkeypatch, environment=environment)

    response = client.post("/tasks/plan", json=TASK_REQUEST)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_returns_401_without_echoing_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted_token = "submitted-secret-token"
    configured_token = "configured-secret-token"
    client = client_with_auth_env(
        monkeypatch,
        environment="production",
        auth_tokens=f"{configured_token}=tasks",
    )

    response = client.post(
        "/tasks/plan",
        json=TASK_REQUEST,
        headers=bearer(submitted_token),
    )

    assert response.status_code == 401
    assert submitted_token not in response.text
    assert configured_token not in response.text


def test_valid_token_with_wrong_capability_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_with_auth_env(monkeypatch, environment="production")

    response = client.post(
        "/tasks/plan",
        json=TASK_REQUEST,
        headers=bearer("fs-token"),
    )

    assert response.status_code == 403


def test_valid_token_with_required_capability_allows_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_with_auth_env(monkeypatch, environment="production")

    response = client.post(
        "/tasks/plan",
        json=TASK_REQUEST,
        headers=bearer("task-token"),
    )

    assert response.status_code == 201


def test_admin_token_allows_multiple_protected_route_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_with_auth_env(monkeypatch, environment="production")
    headers = bearer("admin-token")

    task_response = client.get("/tasks/plans", headers=headers)
    providers_response = client.get("/providers", headers=headers)
    logs_response = client.get("/logs", headers=headers)

    assert task_response.status_code == 200
    assert providers_response.status_code == 200
    assert logs_response.status_code == 200


@pytest.mark.parametrize("path", ["/", "/health", "/docs", "/redoc", "/openapi.json"])
def test_public_routes_remain_public_in_production_auth_mode(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    client = client_with_auth_env(monkeypatch, environment="production")

    response = client.get(path)

    assert response.status_code == 200


def test_explicit_auth_disabled_overrides_staging_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = client_with_auth_env(
        monkeypatch,
        environment="staging",
        auth_enabled="false",
    )

    response = client.post("/tasks/plan", json=TASK_REQUEST)

    assert response.status_code == 201


def test_parse_token_map_handles_semicolons_newlines_and_multiple_capabilities() -> None:
    token_map = parse_token_map("task-token=tasks\nadmin-token=admin,logs;bad;empty=")

    assert token_map == {
        "task-token": frozenset({"tasks"}),
        "admin-token": frozenset({"admin", "logs"}),
    }


def test_auth_configuration_fails_closed_when_enabled_without_tokens() -> None:
    settings = Settings(environment="production", auth_tokens="")

    with pytest.raises(AuthConfigurationError, match="no bearer tokens are configured"):
        validate_auth_configuration(settings)


def test_create_app_fails_closed_when_production_auth_has_no_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "")
    get_settings.cache_clear()

    with pytest.raises(AuthConfigurationError, match="no bearer tokens are configured"):
        create_app()


def test_operator_identity_lifecycle_is_persisted_and_safe(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)

    create_response = client.post(
        "/auth/operators",
        headers=bearer("bootstrap-token"),
        json={
            "operator_id": "operator-alpha",
            "display_name": " Operator Alpha ",
            "role": " reviewer ",
            "capabilities": ["tasks", "logs", "tasks"],
        },
    )
    duplicate_response = client.post(
        "/auth/operators",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "operator-alpha", "capabilities": ["tasks"]},
    )
    list_response = client.get("/auth/operators", headers=bearer("bootstrap-token"))
    get_settings.cache_clear()
    restarted = TestClient(create_app())
    restart_response = restarted.get(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
    )
    update_response = restarted.patch(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
        json={"display_name": "Operator A", "status": "inactive"},
    )
    state_text = (tmp_path / "state" / "operators.json").read_text(encoding="utf-8")
    logs = event_log.list(LogEventType.auth)

    assert create_response.status_code == 201
    assert create_response.json()["id"] == "operator-alpha"
    assert create_response.json()["display_name"] == "Operator Alpha"
    assert create_response.json()["role"] == "reviewer"
    assert create_response.json()["capabilities"] == ["logs", "tasks"]
    assert duplicate_response.status_code == 409
    assert list_response.status_code == 200
    assert "operator-alpha" in list_response.text
    assert restart_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "inactive"
    assert "token_hash" not in create_response.text
    assert "bootstrap-token" not in state_text
    assert "bootstrap-token" not in json.dumps([event.model_dump(mode="json") for event in logs])


def test_operator_group_lifecycle_is_persisted_and_safe(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)

    create_response = client.post(
        "/auth/operator-groups",
        headers=bearer("bootstrap-token"),
        json={
            "group_id": " group-alpha ",
            "display_name": " Operators Alpha ",
            "description": " task operations ",
            "capabilities": ["tasks", "logs", "tasks"],
        },
    )
    duplicate_response = client.post(
        "/auth/operator-groups",
        headers=bearer("bootstrap-token"),
        json={"group_id": "group-alpha", "capabilities": ["tasks"]},
    )
    list_response = client.get("/auth/operator-groups", headers=bearer("bootstrap-token"))
    get_settings.cache_clear()
    restarted = TestClient(create_app())
    restart_response = restarted.get(
        "/auth/operator-groups/group-alpha",
        headers=bearer("bootstrap-token"),
    )
    update_response = restarted.patch(
        "/auth/operator-groups/group-alpha",
        headers=bearer("bootstrap-token"),
        json={
            "display_name": "Operators A",
            "description": "log review",
            "capabilities": ["logs"],
            "status": "inactive",
        },
    )
    state_text = (tmp_path / "state" / "operator-groups.json").read_text(encoding="utf-8")
    logs = event_log.list(LogEventType.auth)

    assert create_response.status_code == 201
    assert create_response.json()["id"] == "group-alpha"
    assert create_response.json()["display_name"] == "Operators Alpha"
    assert create_response.json()["description"] == "task operations"
    assert create_response.json()["capabilities"] == ["logs", "tasks"]
    assert duplicate_response.status_code == 409
    assert list_response.status_code == 200
    assert "group-alpha" in list_response.text
    assert restart_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["display_name"] == "Operators A"
    assert update_response.json()["description"] == "log review"
    assert update_response.json()["capabilities"] == ["logs"]
    assert update_response.json()["status"] == "inactive"
    assert "bootstrap-token" not in state_text
    assert "bootstrap-token" not in json.dumps([event.model_dump(mode="json") for event in logs])


def test_auth_operator_and_token_metadata_redacts_secret_shaped_values(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)

    operator_response = client.post(
        "/auth/operators",
        headers=bearer("bootstrap-token"),
        json={
            "operator_id": "operator-alpha",
            "display_name": "TOKEN=operator-display-secret",
            "role": "password=operator-role-secret",
            "capabilities": ["tasks"],
        },
    )
    token_response = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={
            "operator_id": "operator-alpha",
            "label": "api_key=token-label-secret",
            "capabilities": ["tasks"],
        },
    )
    list_response = client.get("/auth/tokens", headers=bearer("bootstrap-token"))
    state_text = (tmp_path / "state" / "auth-tokens.json").read_text(encoding="utf-8")
    operator_state_text = (tmp_path / "state" / "operators.json").read_text(encoding="utf-8")
    logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.auth)]
    )

    serialized = "\n".join(
        [
            operator_response.text,
            token_response.text,
            list_response.text,
            state_text,
            operator_state_text,
            logs,
        ]
    )

    assert operator_response.status_code == 201
    assert token_response.status_code == 201
    assert "operator-display-secret" not in serialized
    assert "operator-role-secret" not in serialized
    assert "token-label-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_auth_operator_group_metadata_redacts_secret_shaped_values(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)

    create_response = client.post(
        "/auth/operator-groups",
        headers=bearer("bootstrap-token"),
        json={
            "group_id": "group-alpha",
            "display_name": "TOKEN=group-display-secret",
            "description": "password=group-description-secret",
            "capabilities": ["tasks"],
        },
    )
    update_response = client.patch(
        "/auth/operator-groups/group-alpha",
        headers=bearer("bootstrap-token"),
        json={
            "display_name": "api_key=group-updated-display-secret",
            "description": "secret=group-updated-description-secret",
        },
    )
    list_response = client.get("/auth/operator-groups", headers=bearer("bootstrap-token"))
    get_response = client.get(
        "/auth/operator-groups/group-alpha",
        headers=bearer("bootstrap-token"),
    )
    state_text = (tmp_path / "state" / "operator-groups.json").read_text(encoding="utf-8")
    logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.auth)]
    )
    serialized = "\n".join(
        [
            create_response.text,
            update_response.text,
            list_response.text,
            get_response.text,
            state_text,
            logs,
        ]
    )

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert "group-display-secret" not in serialized
    assert "group-description-secret" not in serialized
    assert "group-updated-display-secret" not in serialized
    assert "group-updated-description-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_legacy_persisted_auth_metadata_is_redacted_on_load_and_mutation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def seeded_client(
        scenario: str,
        *,
        token_id: str,
        raw_token: str,
        label: str,
    ) -> tuple[TestClient, Path]:
        root_dir = tmp_path / scenario / "workspace"
        data_dir = tmp_path / scenario / "state"
        root_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        now = datetime.now(UTC).isoformat()
        (data_dir / "operators.json").write_text(
            json.dumps(
                [
                    {
                        "id": "operator-legacy",
                        "display_name": "TOKEN=legacy-display-secret",
                        "role": "password=legacy-role-secret",
                        "capabilities": ["tasks"],
                        "status": "active",
                        "created_at": now,
                        "updated_at": now,
                    }
                ]
            ),
            encoding="utf-8",
        )
        (data_dir / "auth-tokens.json").write_text(
            json.dumps(
                [
                    {
                        "id": token_id,
                        "operator_id": "operator-legacy",
                        "label": label,
                        "token_hash": f"sha256:{sha256(raw_token.encode('utf-8')).hexdigest()}",
                        "capabilities": ["tasks"],
                        "operator_profile_required": True,
                        "status": "active",
                        "created_at": now,
                        "updated_at": now,
                    }
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
        monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
        monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
        monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "bootstrap-token=admin")
        get_settings.cache_clear()
        return TestClient(create_app()), data_dir

    read_client, _read_data_dir = seeded_client(
        "read",
        token_id="auth-token-list",
        raw_token="legacy-list-token",
        label="api_key=legacy-list-secret",
    )
    token_list_response = read_client.get("/auth/tokens", headers=bearer("bootstrap-token"))
    operator_get_response = read_client.get(
        "/auth/operators/operator-legacy",
        headers=bearer("bootstrap-token"),
    )
    operator_list_response = read_client.get("/auth/operators", headers=bearer("bootstrap-token"))
    read_serialized = "\n".join(
        [token_list_response.text, operator_get_response.text, operator_list_response.text]
    )

    assert token_list_response.status_code == 200
    assert operator_get_response.status_code == 200
    assert operator_list_response.status_code == 200
    assert "legacy-list-secret" not in read_serialized
    assert "legacy-display-secret" not in read_serialized
    assert "legacy-role-secret" not in read_serialized
    assert "[REDACTED]" in read_serialized

    for scenario, endpoint, expected_label, leaked_value in [
        (
            "rotate",
            "/auth/tokens/auth-token-rotate/rotate",
            "api_key=[REDACTED]",
            "legacy-rotate-secret",
        ),
        (
            "revoke",
            "/auth/tokens/auth-token-revoke/revoke",
            "TOKEN=[REDACTED]",
            "legacy-revoke-secret",
        ),
        (
            "expire",
            "/auth/tokens/auth-token-expire/expire",
            "password=[REDACTED]",
            "legacy-expire-secret",
        ),
    ]:
        client, data_dir = seeded_client(
            scenario,
            token_id=f"auth-token-{scenario}",
            raw_token=f"legacy-{scenario}-token",
            label=expected_label.replace("[REDACTED]", leaked_value),
        )
        if scenario == "rotate":
            response = client.post(
                endpoint,
                headers=bearer("bootstrap-token"),
                json={"capabilities": ["tasks"]},
            )
            response_label = response.json()["record"]["label"]
        else:
            response = client.post(endpoint, headers=bearer("bootstrap-token"))
            response_label = response.json()["label"]
        state_text = data_dir.joinpath("auth-tokens.json").read_text(encoding="utf-8")
        logs = json.dumps(
            [event.model_dump(mode="json") for event in event_log.list(LogEventType.auth)]
        )
        serialized = "\n".join([response.text, state_text, logs])

        assert response.status_code == 200
        assert response_label == expected_label
        assert leaked_value not in serialized
        assert "[REDACTED]" in serialized

    patch_client, patch_data_dir = seeded_client(
        "operator-patch",
        token_id="auth-token-operator-patch",
        raw_token="legacy-operator-patch-token",
        label="tasks",
    )
    operator_patch_response = patch_client.patch(
        "/auth/operators/operator-legacy",
        headers=bearer("bootstrap-token"),
        json={"status": "inactive"},
    )
    patch_state_text = patch_data_dir.joinpath("operators.json").read_text(encoding="utf-8")
    patch_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.auth)]
    )
    patch_serialized = "\n".join([operator_patch_response.text, patch_state_text, patch_logs])

    assert operator_patch_response.status_code == 200
    assert operator_patch_response.json()["display_name"] == "TOKEN=[REDACTED]"
    assert operator_patch_response.json()["role"] == "password=[REDACTED]"
    assert "legacy-display-secret" not in patch_serialized
    assert "legacy-role-secret" not in patch_serialized
    assert "[REDACTED]" in patch_serialized


def test_operator_assignment_limits_token_issuance(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)

    missing_operator = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "missing-operator", "capabilities": ["tasks"]},
    )
    unknown_capability = client.post(
        "/auth/operators",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "operator-unknown", "capabilities": ["not-real"]},
    )
    create_operator(client, "operator-limited", ["tasks"])
    excessive_token = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "operator-limited", "capabilities": ["tasks", "logs"]},
    )
    allowed_token = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "operator-limited", "capabilities": ["tasks"]},
    )

    assert missing_operator.status_code == 409
    assert unknown_capability.status_code == 422
    assert excessive_token.status_code == 409
    assert allowed_token.status_code == 201


def test_operator_group_assignment_limits_operator_mutations(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator_group(client, "group-alpha", ["logs"])

    unknown_group_create = client.post(
        "/auth/operators",
        headers=bearer("bootstrap-token"),
        json={
            "operator_id": "operator-unknown-group",
            "capabilities": ["tasks"],
            "group_ids": ["missing-group"],
        },
    )
    operator = create_operator(client, "operator-alpha", ["tasks"], group_ids=["group-alpha"])
    unknown_group_update = client.patch(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
        json={"group_ids": ["missing-group"]},
    )
    allowed_update = client.patch(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
        json={"group_ids": ["group-alpha"]},
    )

    assert unknown_group_create.status_code == 409
    assert operator["group_ids"] == ["group-alpha"]
    assert operator["effective_capabilities"] == ["logs", "tasks"]
    assert unknown_group_update.status_code == 409
    assert allowed_update.status_code == 200
    assert allowed_update.json()["group_ids"] == ["group-alpha"]
    assert allowed_update.json()["effective_capabilities"] == ["logs", "tasks"]


def test_operator_group_capabilities_are_inherited_for_token_issuance_and_runtime(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator_group(client, "group-ops", ["logs", "providers"])
    operator = create_operator(client, "operator-alpha", ["tasks"], group_ids=["group-ops"])

    issued = issue_auth_token(client, "operator-alpha", ["logs", "providers"])
    logs_before = client.get("/logs", headers=bearer(issued["token"]))
    reduce_response = client.patch(
        "/auth/operator-groups/group-ops",
        headers=bearer("bootstrap-token"),
        json={"capabilities": ["providers"]},
    )
    operator_after_reduce = client.get(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
    )
    logs_after_reduce = client.get("/logs", headers=bearer(issued["token"]))
    providers_after_reduce = client.get("/providers", headers=bearer(issued["token"]))
    deactivate_response = client.patch(
        "/auth/operator-groups/group-ops",
        headers=bearer("bootstrap-token"),
        json={"status": "inactive"},
    )
    providers_after_deactivate = client.get("/providers", headers=bearer(issued["token"]))

    assert operator["group_ids"] == ["group-ops"]
    assert operator["effective_capabilities"] == ["logs", "providers", "tasks"]
    assert issued["record"]["capabilities"] == ["logs", "providers"]
    assert logs_before.status_code == 200
    assert reduce_response.status_code == 200
    assert operator_after_reduce.status_code == 200
    assert operator_after_reduce.json()["effective_capabilities"] == ["providers", "tasks"]
    assert logs_after_reduce.status_code == 403
    assert providers_after_reduce.status_code == 200
    assert deactivate_response.status_code == 200
    assert providers_after_deactivate.status_code == 401


def test_operator_deactivation_invalidates_linked_persisted_tokens(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    created = issue_auth_token(client, "operator-alpha", ["tasks"])

    active_response = client.post(
        "/tasks/plan",
        headers=bearer(created["token"]),
        json=TASK_REQUEST,
    )
    deactivate_response = client.patch(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
        json={"status": "inactive"},
    )
    inactive_response = client.post(
        "/tasks/plan",
        headers=bearer(created["token"]),
        json=TASK_REQUEST,
    )
    rotate_response = client.post(
        f"/auth/tokens/{created['record']['id']}/rotate",
        headers=bearer("bootstrap-token"),
        json={"capabilities": ["tasks"]},
    )
    new_token_response = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "operator-alpha", "capabilities": ["tasks"]},
    )

    assert active_response.status_code == 201
    assert deactivate_response.status_code == 200
    assert inactive_response.status_code == 401
    assert rotate_response.status_code == 409
    assert new_token_response.status_code == 409
    assert created["token"] not in inactive_response.text


def test_startup_fails_when_only_persisted_token_operator_is_inactive(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    issue_auth_token(client, "operator-alpha", ["tasks"])
    deactivate_response = client.patch(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
        json={"status": "inactive"},
    )
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "")
    get_settings.cache_clear()

    with pytest.raises(AuthConfigurationError, match="no bearer tokens are configured"):
        create_app()

    assert deactivate_response.status_code == 200


def test_operator_capability_reduction_constrains_existing_tokens(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks", "logs"])
    created = issue_auth_token(client, "operator-alpha", ["tasks", "logs"])

    logs_before = client.get("/logs", headers=bearer(created["token"]))
    update_response = client.patch(
        "/auth/operators/operator-alpha",
        headers=bearer("bootstrap-token"),
        json={"capabilities": ["tasks"]},
    )
    tasks_after = client.post(
        "/tasks/plan",
        headers=bearer(created["token"]),
        json=TASK_REQUEST,
    )
    logs_after = client.get("/logs", headers=bearer(created["token"]))

    assert logs_before.status_code == 200
    assert update_response.status_code == 200
    assert tasks_after.status_code == 201
    assert logs_after.status_code == 403


def test_legacy_persisted_tokens_without_operator_profiles_stay_compatible(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    data_dir.mkdir()
    raw_token = "legacy-persisted-token"
    now = datetime.now(UTC).isoformat()
    (data_dir / "auth-tokens.json").write_text(
        json.dumps(
            [
                {
                    "id": "auth-token-legacy",
                    "operator_id": "legacy-operator",
                    "token_hash": f"sha256:{sha256(raw_token.encode('utf-8')).hexdigest()}",
                    "capabilities": ["tasks"],
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.post("/tasks/plan", headers=bearer(raw_token), json=TASK_REQUEST)

    assert response.status_code == 201


def test_persisted_auth_token_is_hashed_returned_once_and_survives_restart(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    create_response = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "operator-alpha", "label": "tasks", "capabilities": ["tasks"]},
    )
    raw_token = create_response.json()["token"]
    token_id = create_response.json()["record"]["id"]
    state_text = (tmp_path / "state" / "auth-tokens.json").read_text(encoding="utf-8")

    task_response = client.post("/tasks/plan", headers=bearer(raw_token), json=TASK_REQUEST)
    list_response = client.get("/auth/tokens", headers=bearer("bootstrap-token"))
    get_settings.cache_clear()
    restarted = TestClient(create_app())
    restarted_task_response = restarted.post(
        "/tasks/plan",
        headers=bearer(raw_token),
        json=TASK_REQUEST,
    )

    assert create_response.status_code == 201
    assert raw_token
    assert create_response.json()["record"]["operator_id"] == "operator-alpha"
    assert "token_hash" not in create_response.json()["record"]
    assert raw_token not in state_text
    assert "pbkdf2-sha256$" in state_text
    assert task_response.status_code == 201
    assert list_response.status_code == 200
    assert raw_token not in list_response.text
    assert token_id in list_response.text
    assert restarted_task_response.status_code == 201


def test_persisted_auth_token_can_bootstrap_production_without_env_tokens(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    created = issue_auth_token(client, "operator-alpha", ["tasks"])
    raw_token = created["token"]
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "")
    get_settings.cache_clear()

    restarted = TestClient(create_app())
    response = restarted.post("/tasks/plan", headers=bearer(raw_token), json=TASK_REQUEST)

    assert response.status_code == 201


def test_persisted_auth_token_rejects_blank_operator_id(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)

    response = client.post(
        "/auth/tokens",
        headers=bearer("bootstrap-token"),
        json={"operator_id": "   ", "capabilities": ["tasks"]},
    )

    assert response.status_code == 422


def test_persisted_token_rotation_revokes_old_token_without_secret_echo(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    created = issue_auth_token(client, "operator-alpha", ["tasks"])
    raw_token = created["token"]
    token_id = created["record"]["id"]

    rotate_response = client.post(
        f"/auth/tokens/{token_id}/rotate",
        headers=bearer("bootstrap-token"),
        json={"label": "rotated", "capabilities": ["tasks"]},
    )
    rotated = rotate_response.json()
    old_response = client.post("/tasks/plan", headers=bearer(raw_token), json=TASK_REQUEST)
    new_response = client.post(
        "/tasks/plan",
        headers=bearer(rotated["token"]),
        json=TASK_REQUEST,
    )
    logs = event_log.list(LogEventType.auth)

    assert rotate_response.status_code == 200
    assert rotated["record"]["rotated_from_token_id"] == token_id
    assert old_response.status_code == 401
    assert new_response.status_code == 201
    serialized_logs = json.dumps([event.model_dump(mode="json") for event in logs])
    assert raw_token not in serialized_logs
    assert rotated["token"] not in serialized_logs


def test_persisted_token_rotation_preserves_existing_expiry_by_default(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    created = issue_auth_token(
        client,
        "operator-alpha",
        ["tasks"],
        expires_at=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
    )

    rotate_response = client.post(
        f"/auth/tokens/{created['record']['id']}/rotate",
        headers=bearer("bootstrap-token"),
        json={"capabilities": ["tasks"]},
    )

    assert rotate_response.status_code == 200
    assert rotate_response.json()["record"]["expires_at"] == created["record"]["expires_at"]


def test_persisted_token_rotation_rejects_inactive_records(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    revoked = issue_auth_token(client, "operator-alpha", ["tasks"])
    expired = issue_auth_token(
        client,
        "operator-alpha",
        ["tasks"],
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    )
    client.post(
        f"/auth/tokens/{revoked['record']['id']}/revoke",
        headers=bearer("bootstrap-token"),
    )

    revoked_rotate = client.post(
        f"/auth/tokens/{revoked['record']['id']}/rotate",
        headers=bearer("bootstrap-token"),
        json={"capabilities": ["tasks"]},
    )
    expired_rotate = client.post(
        f"/auth/tokens/{expired['record']['id']}/rotate",
        headers=bearer("bootstrap-token"),
        json={"capabilities": ["tasks"]},
    )

    assert revoked_rotate.status_code == 409
    assert expired_rotate.status_code == 409
    assert revoked["token"] not in revoked_rotate.text
    assert expired["token"] not in expired_rotate.text


def test_persisted_revoked_and_expired_tokens_are_rejected_without_secret_echo(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    active = issue_auth_token(client, "operator-alpha", ["tasks"])
    sibling = issue_auth_token(client, "operator-alpha", ["tasks"])
    expired = issue_auth_token(
        client,
        "operator-alpha",
        ["tasks"],
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
    )

    revoke_response = client.post(
        f"/auth/tokens/{active['record']['id']}/revoke",
        headers=bearer("bootstrap-token"),
    )
    revoked_response = client.post(
        "/tasks/plan",
        headers=bearer(active["token"]),
        json=TASK_REQUEST,
    )
    sibling_response = client.post(
        "/tasks/plan",
        headers=bearer(sibling["token"]),
        json=TASK_REQUEST,
    )
    expired_response = client.post(
        "/tasks/plan",
        headers=bearer(expired["token"]),
        json=TASK_REQUEST,
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "revoked"
    assert "token" not in revoke_response.json()
    assert revoked_response.status_code == 401
    assert active["token"] not in revoked_response.text
    assert sibling_response.status_code == 201
    assert expired_response.status_code == 401
    assert expired["token"] not in expired_response.text


def test_persisted_token_expire_endpoint_rejects_token_without_secret_echo(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-alpha", ["tasks"])
    created = issue_auth_token(client, "operator-alpha", ["tasks"])

    expire_response = client.post(
        f"/auth/tokens/{created['record']['id']}/expire",
        headers=bearer("bootstrap-token"),
    )
    rejected_response = client.post(
        "/tasks/plan",
        headers=bearer(created["token"]),
        json=TASK_REQUEST,
    )

    assert expire_response.status_code == 200
    assert expire_response.json()["status"] == "expired"
    assert "token" not in expire_response.json()
    assert rejected_response.status_code == 401
    assert created["token"] not in rejected_response.text


def test_persisted_token_expiry_accepts_naive_datetime_as_utc(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    expired_at = (datetime.now(UTC) - timedelta(seconds=1)).replace(tzinfo=None).isoformat()
    create_operator(client, "operator-alpha", ["tasks"])
    created = issue_auth_token(
        client,
        "operator-alpha",
        ["tasks"],
        expires_at=expired_at,
    )

    expired_response = client.post(
        "/tasks/plan",
        headers=bearer(created["token"]),
        json=TASK_REQUEST,
    )

    assert expired_response.status_code == 401


def test_persisted_token_capabilities_and_env_tokens_can_coexist(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-fs", ["filesystem"])
    created = issue_auth_token(client, "operator-fs", ["filesystem"])

    wrong_capability = client.post(
        "/tasks/plan",
        headers=bearer(created["token"]),
        json=TASK_REQUEST,
    )
    env_token_response = client.post(
        "/tasks/plan",
        headers=bearer("bootstrap-token"),
        json=TASK_REQUEST,
    )
    state_text = (tmp_path / "state" / "auth-tokens.json").read_text(encoding="utf-8")

    assert wrong_capability.status_code == 403
    assert env_token_response.status_code == 201
    assert "bootstrap-token" not in state_text


def test_auth_token_management_requires_auth_capability(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-task", ["tasks"])
    create_operator(client, "operator-auth", ["auth"])
    task_token = issue_auth_token(client, "operator-task", ["tasks"])
    auth_token = issue_auth_token(client, "operator-auth", ["auth"])

    forbidden_list = client.get("/auth/tokens", headers=bearer(task_token["token"]))
    allowed_list = client.get("/auth/tokens", headers=bearer(auth_token["token"]))
    forbidden_create = client.post(
        "/auth/tokens",
        headers=bearer(task_token["token"]),
        json={"operator_id": "operator-new", "capabilities": ["tasks"]},
    )

    assert forbidden_list.status_code == 403
    assert allowed_list.status_code == 200
    assert forbidden_create.status_code == 403


def test_credential_reference_lifecycle_requires_capability_and_never_stores_secret(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGENTIC_TEST_EXTERNAL_KEY", "external-api-key-secret")
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-task", ["tasks"])
    create_operator(client, "operator-credential", ["credentials"])
    task_token = issue_auth_token(client, "operator-task", ["tasks"])
    credential_token = issue_auth_token(client, "operator-credential", ["credentials"])

    forbidden_create = client.post(
        "/credentials/references",
        headers=bearer(task_token["token"]),
        json={"env_var": "DGENTIC_TEST_EXTERNAL_KEY", "label": "external provider"},
    )
    create_response = client.post(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
        json={"env_var": "DGENTIC_TEST_EXTERNAL_KEY", "label": "external provider"},
    )
    ref_id = create_response.json()["id"]
    list_response = client.get(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
    )
    resolved_env_var = credential_env_for_reference(ref_id)
    revoke_response = client.post(
        f"/credentials/references/{ref_id}/revoke",
        headers=bearer(credential_token["token"]),
    )
    state_text = (tmp_path / "state" / "credential-references.json").read_text(encoding="utf-8")
    logs = event_log.list(LogEventType.credential)

    assert forbidden_create.status_code == 403
    assert create_response.status_code == 201
    assert create_response.json()["env_var"] == "DGENTIC_TEST_EXTERNAL_KEY"
    assert "external-api-key-secret" not in create_response.text
    assert list_response.status_code == 200
    assert "external-api-key-secret" not in list_response.text
    assert resolved_env_var == "DGENTIC_TEST_EXTERNAL_KEY"
    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "revoked"
    assert "external-api-key-secret" not in state_text
    assert "external-api-key-secret" not in json.dumps(
        [event.model_dump(mode="json") for event in logs]
    )


def test_external_process_credential_reference_lifecycle_is_metadata_only(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-credential", ["credentials"])
    credential_token = issue_auth_token(client, "operator-credential", ["credentials"])

    create_response = client.post(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
        json={
            "source_type": "external_process",
            "adapter_id": "process-vault",
            "secret_name": "providers/openai",
            "label": "process provider",
        },
    )
    ref_id = create_response.json()["id"]
    list_response = client.get(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
    )
    revoke_response = client.post(
        f"/credentials/references/{ref_id}/revoke",
        headers=bearer(credential_token["token"]),
    )
    invalid_response = client.post(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
        json={
            "source_type": "external_process",
            "env_var": "DGENTIC_TEST_EXTERNAL_KEY",
            "adapter_id": "process-vault",
            "secret_name": "providers/openai",
        },
    )
    state_text = (tmp_path / "state" / "credential-references.json").read_text(encoding="utf-8")

    assert create_response.status_code == 201
    assert create_response.json()["source_type"] == "external_process"
    assert create_response.json()["env_var"] == ""
    assert create_response.json()["adapter_id"] == "process-vault"
    assert create_response.json()["secret_name"] == "providers/openai"
    assert list_response.status_code == 200
    assert "external_process" in list_response.text
    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "revoked"
    assert invalid_response.status_code == 422
    assert "external-process-secret" not in create_response.text
    assert "external-process-secret" not in list_response.text
    assert "external-process-secret" not in state_text


def test_local_vault_credential_reference_lifecycle_encrypts_secret(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_secret = "local-vault-api-key-secret"
    monkeypatch.setenv("DGENTIC_CREDENTIAL_VAULT_KEY", Fernet.generate_key().decode("ascii"))
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-credential", ["credentials"])
    credential_token = issue_auth_token(client, "operator-credential", ["credentials"])

    create_response = client.post(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
        json={
            "source_type": "local_vault",
            "secret_value": raw_secret,
            "label": "local vault provider",
        },
    )
    ref_id = create_response.json()["id"]
    resolved_secret = credential_secret_for_reference(ref_id, purpose="provider")
    list_response = client.get(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
    )
    revoke_response = client.post(
        f"/credentials/references/{ref_id}/revoke",
        headers=bearer(credential_token["token"]),
    )
    state_text = (tmp_path / "state" / "credential-references.json").read_text(encoding="utf-8")
    logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.credential)]
    )
    serialized_api = "\n".join([create_response.text, list_response.text, revoke_response.text])

    assert create_response.status_code == 201
    assert create_response.json()["source_type"] == "local_vault"
    assert create_response.json()["env_var"] == ""
    assert create_response.json()["adapter_id"] == ""
    assert create_response.json()["secret_name"] == ""
    assert resolved_secret == raw_secret
    assert list_response.status_code == 200
    assert revoke_response.status_code == 200
    assert revoke_response.json()["status"] == "revoked"
    assert "encrypted_secret" in state_text
    assert raw_secret not in serialized_api
    assert raw_secret not in state_text
    assert raw_secret not in logs
    assert "encrypted_secret" not in serialized_api


def test_local_vault_credential_reference_requires_operator_key_without_secret_echo(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_secret = "missing-vault-key-secret"
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-credential", ["credentials"])
    credential_token = issue_auth_token(client, "operator-credential", ["credentials"])

    create_response = client.post(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
        json={
            "source_type": "local_vault",
            "secret_value": raw_secret,
            "label": "local vault provider",
        },
    )
    state_file = tmp_path / "state" / "credential-references.json"
    state_text = state_file.read_text(encoding="utf-8") if state_file.exists() else ""
    logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.credential)]
    )

    assert create_response.status_code == 400
    assert "Credential reference is invalid" in create_response.text
    assert "Credential vault key is not configured" not in create_response.text
    assert raw_secret not in create_response.text
    assert raw_secret not in state_text
    assert raw_secret not in logs


def test_credential_reference_label_redacts_secret_shaped_values(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGENTIC_TEST_EXTERNAL_KEY", "external-api-key-secret")
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-credential", ["credentials"])
    credential_token = issue_auth_token(client, "operator-credential", ["credentials"])

    create_response = client.post(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
        json={
            "env_var": "DGENTIC_TEST_EXTERNAL_KEY",
            "label": "api_key=credential-label-secret",
        },
    )
    list_response = client.get(
        "/credentials/references",
        headers=bearer(credential_token["token"]),
    )
    state_text = (tmp_path / "state" / "credential-references.json").read_text(encoding="utf-8")
    logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.credential)]
    )
    serialized = "\n".join([create_response.text, list_response.text, state_text, logs])

    assert create_response.status_code == 201
    assert "credential-label-secret" not in serialized
    assert "external-api-key-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_legacy_credential_reference_label_is_redacted_on_load_and_mutation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    data_dir.mkdir()
    now = datetime.now(UTC).isoformat()
    monkeypatch.setenv("DGENTIC_LEGACY_EXTERNAL_KEY", "legacy-env-secret")
    (data_dir / "credential-references.json").write_text(
        json.dumps(
            [
                {
                    "id": "credential-ref-legacy",
                    "env_var": "DGENTIC_LEGACY_EXTERNAL_KEY",
                    "label": "api_key=legacy-credential-secret",
                    "purpose": "provider",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "bootstrap-token=admin")
    get_settings.cache_clear()
    client = TestClient(create_app())

    list_response = client.get("/credentials/references", headers=bearer("bootstrap-token"))
    revoke_response = client.post(
        "/credentials/references/credential-ref-legacy/revoke",
        headers=bearer("bootstrap-token"),
    )
    state_text = (data_dir / "credential-references.json").read_text(encoding="utf-8")
    logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.credential)]
    )
    serialized = "\n".join([list_response.text, revoke_response.text, state_text, logs])

    assert list_response.status_code == 200
    assert revoke_response.status_code == 200
    assert list_response.json()[0]["label"] == "api_key=[REDACTED]"
    assert revoke_response.json()["label"] == "api_key=[REDACTED]"
    assert "legacy-credential-secret" not in serialized
    assert "legacy-env-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_persisted_token_uses_operator_id_for_approval_requesters_and_decisions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "DGENTIC_TEST_EXTERNAL")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-test")
    monkeypatch.setenv("DGENTIC_TEST_EXTERNAL", "secret-value")
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps({"rules": [{"domain": "network.example.test", "mode": "approval_required"}]}),
    )
    client = production_client_with_state(tmp_path, monkeypatch)
    create_operator(client, "operator-approver", ["cli", "approvals", "tools"])
    created = issue_auth_token(client, "operator-approver", ["cli", "approvals", "tools"])
    headers = bearer(created["token"])
    tool_dir = tmp_path / "workspace" / "localmcp" / "auth-approval-tool"
    tool_dir.mkdir(parents=True)
    (tool_dir / "wrapper.py").write_text(
        "def run(payload):\n    return {'ok': True}\n",
        encoding="utf-8",
    )

    approval_response = client.post(
        "/cli/approvals?requested_by=tester",
        headers=headers,
        json={"command": "python --version", "timeout_seconds": 10},
    )
    approve_response = client.post(
        f"/cli/approvals/{approval_response.json()['id']}/approve",
        headers=headers,
        json={"decided_by": "spoofed-reviewer"},
    )
    provider_approval_response = client.post(
        "/providers/external-openai-compatible/approvals?requested_by=provider-spoof",
        headers=headers,
        json={
            "provider_id": "external-openai-compatible",
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    create_tool_response = client.post(
        "/tools",
        headers=headers,
        json={
            "name": "auth-approval-tool",
            "description": "Approval requester binding test tool.",
            "entrypoint": "wrapper.py",
            "permission_mode": "approval_required",
        },
    )
    tool_approval_response = client.post(
        "/tools/auth-approval-tool/approvals?requested_by=tool-spoof",
        headers=headers,
        json={"payload": {"ok": True}, "timeout_seconds": 5},
    )
    network_approval_response = client.post(
        "/network/approvals",
        headers=headers,
        json={"url": "https://network.example.test/v1", "requested_by": "network-spoof"},
    )
    network_approve_response = client.post(
        f"/network/approvals/{network_approval_response.json()['id']}/approve",
        headers=headers,
        json={"decided_by": "network-reviewer-spoof"},
    )

    assert approval_response.status_code == 201
    assert approval_response.json()["requested_by"] == "operator-approver"
    assert approve_response.status_code == 200
    assert approve_response.json()["decided_by"] == "operator-approver"
    assert provider_approval_response.status_code == 201
    assert provider_approval_response.json()["requested_by"] == "operator-approver"
    assert create_tool_response.status_code == 201
    assert tool_approval_response.status_code == 201
    assert tool_approval_response.json()["requested_by"] == "operator-approver"
    assert network_approval_response.status_code == 201
    assert network_approval_response.json()["requested_by"] == "operator-approver"
    assert network_approve_response.status_code == 200
    assert network_approve_response.json()["decided_by"] == "operator-approver"


@pytest.mark.parametrize(
    ("path", "capability"),
    [
        ("/", None),
        ("/health", None),
        ("/tasks/plan", "tasks"),
        ("/auth/tokens", "auth"),
        ("/credentials/references", "credentials"),
        ("/guardrails/network", "network"),
        ("/network/approvals", "approvals"),
        ("/filesystem/read", "filesystem"),
        ("/filesystem/delete", "filesystem"),
        ("/cli/runs", "cli"),
        ("/providers", "providers"),
        ("/providers/external-openai-compatible/approvals", "approvals"),
        ("/providers/approvals/provider-approval-1/approve", "approvals"),
        ("/agents/agent-1", "agents"),
        ("/api/v1/memory/metadata", "memory"),
        ("/tools/approvals/approval-1/approve", "approvals"),
        ("/api/v1/tools/registry", "tools"),
        ("/sessions/summary", "sessions"),
        ("/logs", "logs"),
        ("/unmapped-sensitive-route", "admin"),
    ],
)
def test_capability_for_path_maps_public_and_sensitive_routes(
    path: str,
    capability: str | None,
) -> None:
    assert capability_for_path(path) == capability


@pytest.mark.parametrize(
    ("method", "path", "capability"),
    [
        ("POST", "/cli/approvals", "cli"),
        ("GET", "/cli/approvals", "approvals"),
        ("GET", "/cli/approvals/approval-1/review", "approvals"),
        ("POST", "/cli/approvals/approval-1/approve", "approvals"),
        ("POST", "/cli/approvals/approval-1/deny", "approvals"),
        ("POST", "/cli/approvals/approval-1/execute", "cli"),
        ("GET", "/cli/runs", "cli"),
    ],
)
def test_capability_for_request_splits_cli_approval_review_from_execution(
    method: str,
    path: str,
    capability: str | None,
) -> None:
    assert capability_for_request(method, path) == capability


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (Settings(environment="development"), False),
        (Settings(environment="production"), True),
        (Settings(environment="staging"), True),
        (Settings(environment="staging", auth_enabled=False), False),
        (Settings(environment="development", auth_enabled=True), True),
    ],
)
def test_effective_auth_enabled_defaults_and_explicit_overrides(
    settings: Settings,
    expected: bool,
) -> None:
    assert settings.effective_auth_enabled is expected
