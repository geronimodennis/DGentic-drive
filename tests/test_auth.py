import pytest
from fastapi.testclient import TestClient

from dgentic.auth import (
    AuthConfigurationError,
    capability_for_path,
    parse_token_map,
    validate_auth_configuration,
)
from dgentic.main import create_app
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


@pytest.mark.parametrize(
    ("path", "capability"),
    [
        ("/", None),
        ("/health", None),
        ("/tasks/plan", "tasks"),
        ("/filesystem/read", "filesystem"),
        ("/filesystem/delete", "filesystem"),
        ("/cli/runs", "cli"),
        ("/providers", "providers"),
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
