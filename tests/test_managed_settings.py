import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from dgentic.auth import AuthConfigurationError
from dgentic.main import create_app
from dgentic.network_policy import evaluate_network_domain_policy
from dgentic.settings import ManagedSettingsError, get_effective_settings_view, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _write_managed_settings(tmp_path, payload: dict) -> tuple[str, str]:
    raw_payload = json.dumps(payload)
    path = tmp_path / "managed-settings.json"
    path.write_text(raw_payload, encoding="utf-8")
    return str(path), raw_payload


def _settings_by_name(response_payload: dict) -> dict[str, dict]:
    return {item["name"]: item for item in response_payload["settings"]}


def test_managed_settings_override_environment_and_report_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("DGENTIC_NETWORK_DOMAIN_POLICY", '{"default_mode":"allow"}')
    managed_path, raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "max_filesystem_bytes": 4096,
                "network_domain_policy": {
                    "default_mode": "deny",
                    "rules": [{"domain": "api.example.test", "mode": "allow"}],
                },
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    settings = get_settings()
    assert settings.max_filesystem_bytes == 4096
    assert json.loads(settings.network_domain_policy)["default_mode"] == "deny"

    exact = evaluate_network_domain_policy("https://api.example.test/v1")
    fallback = evaluate_network_domain_policy("https://other.example.test/v1")
    assert exact.allowed is True
    assert exact.mode == "allow"
    assert fallback.allowed is False
    assert fallback.mode == "deny"

    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    assert view.managed_settings_enabled is True
    assert view.managed_settings_digest == sha256(raw_payload.encode("utf-8")).hexdigest()
    assert view.managed_fields == ["max_filesystem_bytes", "network_domain_policy"]
    assert fields["network_domain_policy"].source == "managed"
    assert fields["max_filesystem_bytes"].source == "managed"
    assert fields["root_dir"].source == "environment"
    assert fields["effective_auth_enabled"].source == "derived"


def test_managed_settings_fall_back_to_environment_and_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("DGENTIC_MAX_FILESYSTEM_BYTES", "2048")
    monkeypatch.delenv("DGENTIC_MANAGED_SETTINGS_FILE", raising=False)

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}

    assert settings.max_filesystem_bytes == 2048
    assert view.managed_settings_enabled is False
    assert view.managed_fields == []
    assert fields["max_filesystem_bytes"].source == "environment"
    assert fields["network_domain_policy"].source == "default"


@pytest.mark.parametrize(
    ("payload", "error_match"),
    [
        ("not-json", "valid JSON"),
        ({"unexpected": {}}, "settings object"),
        ({"settings": {"root_dir": "/tmp/other"}}, "not supported"),
        ({"settings": {"unknown_setting": True}}, "Unknown managed settings field"),
        ({"settings": {"managed_settings_file": "nested.json"}}, "reserved"),
        ({"settings": {"app_name": "TOKEN=raw-secret"}}, "secret-shaped"),
    ],
)
def test_malformed_managed_settings_fail_closed(
    tmp_path,
    monkeypatch,
    payload: str | dict,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    path = tmp_path / "managed-settings.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", str(path))

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


def test_managed_auth_enabled_overrides_env_disable_and_fails_closed(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "")
    (tmp_path / "workspace").mkdir()
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"auth_enabled": True}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    assert get_settings().effective_auth_enabled is True
    with pytest.raises(AuthConfigurationError):
        create_app()


def test_managed_settings_cannot_disable_already_effective_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"auth_enabled": False}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match="cannot disable"):
        get_settings()


def test_effective_settings_api_requires_admin_and_redacts_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_TOKENS", "admin-token=admin;task-token=tasks")
    (tmp_path / "workspace").mkdir()
    managed_path, raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "app_name": "Managed DGentic",
                "auth_enabled": True,
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    client = TestClient(create_app())
    missing_response = client.get("/settings/effective")
    forbidden_response = client.get(
        "/settings/effective",
        headers={"Authorization": "Bearer task-token"},
    )
    allowed_response = client.get(
        "/settings/effective",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert missing_response.status_code == 401
    assert forbidden_response.status_code == 403
    assert allowed_response.status_code == 200
    payload = allowed_response.json()
    fields = _settings_by_name(payload)
    assert payload["managed_settings_enabled"] is True
    assert payload["managed_settings_digest"] == sha256(raw_payload.encode("utf-8")).hexdigest()
    assert fields["app_name"]["value"] == "Managed DGentic"
    assert fields["app_name"]["source"] == "managed"
    assert fields["auth_tokens"]["value"] == "[REDACTED]"
    assert fields["auth_tokens"]["redacted"] is True
    assert fields["auth_tokens"]["source"] == "environment"
