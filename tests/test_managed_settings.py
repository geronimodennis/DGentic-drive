import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from dgentic.auth import AuthConfigurationError
from dgentic.credentials import credential_secret_manager_adapters
from dgentic.main import create_app
from dgentic.network_policy import evaluate_network_domain_policy
from dgentic.redaction import REDACTED_SECRET_MARKER
from dgentic.settings import (
    ManagedSettingsError,
    get_effective_settings_view,
    get_settings,
    managed_cli_policy_rules,
    managed_command_recipes,
    managed_credential_references,
    managed_hook_policy_rules,
    managed_network_domain_policy_rules,
    managed_plugin_component_records,
    managed_plugin_trust_records,
    managed_policy_locks,
    require_managed_policy_surface_mutable,
)


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


def test_managed_policy_locks_apply_only_from_managed_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("DGENTIC_MANAGED_POLICY_LOCKS", '["cli_policy"]')

    assert managed_policy_locks() == frozenset()
    require_managed_policy_surface_mutable("cli_policy")

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_policy_locks": [
                    "cli-policy",
                    "hook policy",
                    "network policy",
                    "plugin components",
                    "plugin hook policies",
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    assert managed_policy_locks() == frozenset(
        {"cli_policy", "hook_policy", "plugin_components", "plugin_hook_policies"}
        | {"network_policy"}
    )
    with pytest.raises(PermissionError, match="cli_policy"):
        require_managed_policy_surface_mutable("cli_policy")
    with pytest.raises(PermissionError, match="plugin_hook_policies"):
        require_managed_policy_surface_mutable("plugin_hook_policies")
    with pytest.raises(PermissionError, match="plugin_components"):
        require_managed_policy_surface_mutable("plugin_components")
    with pytest.raises(PermissionError, match="network_policy"):
        require_managed_policy_surface_mutable("network_policy")
    require_managed_policy_surface_mutable("command_recipes")


def test_managed_network_domain_policy_rules_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_NETWORK_DOMAIN_POLICY_RULES",
        json.dumps(
            [
                {
                    "id": "env.network-deny",
                    "domain": "env.example.test",
                    "mode": "deny",
                }
            ]
        ),
    )

    assert managed_network_domain_policy_rules() == ()
    env_decision = evaluate_network_domain_policy("https://env.example.test/v1")
    assert env_decision.mode == "allow"

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_network_domain_policy_rules": [
                    {
                        "id": "managed.wildcard-deny",
                        "domain": "*.corp.example.test",
                        "mode": "deny",
                        "reason": "Managed wildcard deny.",
                        "priority": 20,
                    },
                    {
                        "id": "managed.exact-allow",
                        "domain": "api.corp.example.test",
                        "mode": "allow",
                        "reason": "Managed exact allow.",
                        "priority": 20,
                    },
                    {
                        "id": "managed.disabled-deny",
                        "domain": "disabled.example.test",
                        "mode": "deny",
                        "enabled": False,
                    },
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    records = managed_network_domain_policy_rules()
    exact = evaluate_network_domain_policy("https://api.corp.example.test/v1")
    wildcard = evaluate_network_domain_policy("https://worker.corp.example.test/v1")
    disabled = evaluate_network_domain_policy("https://disabled.example.test/v1")

    assert json.loads(settings.managed_network_domain_policy_rules)[0]["id"] == (
        "managed.wildcard-deny"
    )
    assert fields["managed_network_domain_policy_rules"].source == "managed"
    assert view.managed_fields == ["managed_network_domain_policy_rules"]
    assert [record.id for record in records] == [
        "managed.exact-allow",
        "managed.wildcard-deny",
        "managed.disabled-deny",
    ]
    assert exact.mode == "allow"
    assert exact.matched_rule_id == "managed.exact-allow"
    assert exact.matched_rule_source == "managed"
    assert wildcard.mode == "deny"
    assert wildcard.matched_rule_id == "managed.wildcard-deny"
    assert disabled.mode == "allow"
    assert disabled.matched_rule_id is None


@pytest.mark.parametrize(
    "rules_payload",
    [
        {"id": "not-a-list"},
        ["not-an-object"],
        [{"id": "managed.unknown", "domain": "api.example.test", "mode": "deny", "extra": True}],
        [{"domain": "api.example.test", "mode": "deny"}],
        [{"id": "managed.bad-domain", "domain": "bad/path", "mode": "deny"}],
        [{"id": "managed.bad-mode", "domain": "api.example.test", "mode": "prompt"}],
        [
            {"id": "managed.duplicate", "domain": "api.example.test", "mode": "deny"},
            {"id": "managed.duplicate", "domain": "other.example.test", "mode": "deny"},
        ],
        [
            {"id": "managed.one", "domain": "api.example.test", "mode": "deny"},
            {"id": "managed.two", "domain": "API.EXAMPLE.TEST.", "mode": "allow"},
        ],
        [
            {
                "id": "managed.secret-reason",
                "domain": "api.example.test",
                "mode": "deny",
                "reason": "TOKEN=raw-secret",
            }
        ],
        [
            {
                "id": "managed.bad-enabled",
                "domain": "api.example.test",
                "mode": "deny",
                "enabled": "yes",
            }
        ],
        [
            {
                "id": "managed.bad-priority",
                "domain": "api.example.test",
                "mode": "deny",
                "priority": 10_001,
            }
        ],
        [
            {
                "id": f"managed.too-many-{index}",
                "domain": f"host-{index}.example.test",
                "mode": "deny",
            }
            for index in range(101)
        ],
    ],
)
def test_managed_network_domain_policy_rules_fail_closed(
    tmp_path,
    monkeypatch,
    rules_payload,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_network_domain_policy_rules": rules_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError):
        get_settings()


def test_managed_plugin_trust_records_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_PLUGIN_TRUST_RECORDS",
        json.dumps(
            [
                {
                    "plugin_id": "env-plugin",
                    "manifest_digest": "a" * 64,
                    "status": "trusted",
                    "reason": "Environment trust is not managed.",
                }
            ]
        ),
    )

    assert managed_plugin_trust_records() == ()

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_plugin_trust_records": [
                    {
                        "plugin_id": "managed-plugin",
                        "manifest_digest": "B" * 64,
                        "status": "trusted",
                        "reason": "Deployment reviewed manifest digest.",
                        "decided_by": "platform-security",
                    }
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    records = managed_plugin_trust_records()

    assert json.loads(settings.managed_plugin_trust_records)[0]["plugin_id"] == "managed-plugin"
    assert fields["managed_plugin_trust_records"].source == "managed"
    assert view.managed_fields == ["managed_plugin_trust_records"]
    assert len(records) == 1
    assert records[0].plugin_id == "managed-plugin"
    assert records[0].manifest_digest == "b" * 64
    assert records[0].status == "trusted"
    assert records[0].decided_by == "platform-security"


def test_managed_plugin_component_records_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_PLUGIN_COMPONENT_RECORDS",
        json.dumps(
            [
                {
                    "plugin_id": "env-plugin",
                    "component_type": "tools",
                    "name": "Environment component",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ]
        ),
    )

    assert managed_plugin_component_records() == ()

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_plugin_component_records": [
                    {
                        "plugin_id": "managed-plugin",
                        "component_type": "tools",
                        "name": "Managed scanner",
                        "manifest_digest": "c" * 64,
                        "component_path": "tools/scanner.json",
                        "component_digest": "d" * 64,
                        "component_size_bytes": 42,
                    }
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    records = managed_plugin_component_records()

    assert json.loads(settings.managed_plugin_component_records)[0]["plugin_id"] == (
        "managed-plugin"
    )
    assert fields["managed_plugin_component_records"].source == "managed"
    assert view.managed_fields == ["managed_plugin_component_records"]
    assert len(records) == 1
    assert records[0].component_id.startswith("managed-plugin.component-")
    assert records[0].plugin_id == "managed-plugin"
    assert records[0].component_type == "tools"
    assert records[0].name == "Managed scanner"
    assert records[0].component_path == "tools/scanner.json"
    assert records[0].source == "managed"
    assert records[0].installed_by == "managed"


def test_managed_credential_reference_records_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_CREDENTIAL_REFERENCES",
        json.dumps(
            [
                {
                    "id": "env.credential",
                    "source_type": "env",
                    "env_var": "DGENTIC_ENV_IGNORED",
                    "purpose": "provider",
                    "status": "active",
                }
            ]
        ),
    )

    assert managed_credential_references() == ()

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_credential_references": [
                    {
                        "id": "managed.provider-env",
                        "source_type": "env",
                        "env_var": "DGENTIC_MANAGED_PROVIDER_KEY",
                        "label": "Managed provider key",
                        "purpose": "provider",
                        "status": "active",
                    },
                    {
                        "id": "managed.runtime-process",
                        "source_type": "external_process",
                        "adapter_id": "platform-vault",
                        "secret_name": "runtime/worker",
                        "purpose": "runtime",
                        "status": "revoked",
                    },
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    records = managed_credential_references()

    assert json.loads(settings.managed_credential_references)[0]["id"] == "managed.provider-env"
    assert fields["managed_credential_references"].source == "managed"
    assert fields["managed_credential_references"].redacted is True
    assert view.managed_fields == ["managed_credential_references"]
    assert [record.id for record in records] == [
        "managed.provider-env",
        "managed.runtime-process",
    ]
    assert records[0].source == "managed"
    assert records[0].source_type == "env"
    assert records[0].env_var == "DGENTIC_MANAGED_PROVIDER_KEY"
    assert records[0].label == "Managed provider key"
    assert records[1].source == "managed"
    assert records[1].source_type == "external_process"
    assert records[1].adapter_id == "platform-vault"
    assert records[1].secret_name == "runtime/worker"


def test_managed_secret_manager_adapters_and_references_apply_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "credential_secret_manager_adapters": {
                    "vault-main": {
                        "type": "hashicorp_vault_kv2",
                        "base_url": "https://vault.example.test/v1/",
                        "mount": "secret",
                        "field": "api_key",
                        "token_env_var": "DGENTIC_VAULT_TOKEN",
                        "timeout_seconds": 1.5,
                        "max_response_bytes": 2048,
                    }
                },
                "credential_secret_manager_allowed_base_urls": ("https://vault.example.test/v1/"),
                "managed_credential_references": [
                    {
                        "id": "managed.provider-vault",
                        "source_type": "secret_manager",
                        "adapter_id": "vault-main",
                        "secret_name": "providers/openai",
                        "label": "Managed Vault provider",
                        "purpose": "provider",
                        "status": "active",
                    }
                ],
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    records = managed_credential_references()
    adapters = credential_secret_manager_adapters(settings)

    assert view.managed_fields == [
        "credential_secret_manager_adapters",
        "credential_secret_manager_allowed_base_urls",
        "managed_credential_references",
    ]
    assert fields["credential_secret_manager_adapters"].source == "managed"
    assert fields["credential_secret_manager_adapters"].redacted is True
    assert fields["credential_secret_manager_adapters"].value == REDACTED_SECRET_MARKER
    assert fields["credential_secret_manager_allowed_base_urls"].source == "managed"
    assert fields["credential_secret_manager_allowed_base_urls"].redacted is True
    assert fields["credential_secret_manager_allowed_base_urls"].value == REDACTED_SECRET_MARKER
    assert fields["managed_credential_references"].source == "managed"
    assert fields["managed_credential_references"].redacted is True
    assert fields["managed_credential_references"].value == REDACTED_SECRET_MARKER
    assert records[0].source == "managed"
    assert records[0].source_type == "secret_manager"
    assert records[0].adapter_id == "vault-main"
    assert records[0].secret_name == "providers/openai"
    assert adapters["vault-main"].base_url == "https://vault.example.test/v1"
    assert adapters["vault-main"].field == "api_key"
    assert adapters["vault-main"].token_env_var == "DGENTIC_VAULT_TOKEN"
    assert "DGENTIC_VAULT_TOKEN" in settings.credential_secret_manager_adapters


@pytest.mark.parametrize(
    "adapters_payload",
    [
        {"vault/main": {"base_url": "https://vault.example.test", "token_env_var": "VAULT_TOKEN"}},
        {"vault-main": "https://vault.example.test"},
        {"vault-main": {"base_url": "http://vault.example.test", "token_env_var": "VAULT_TOKEN"}},
        {
            "vault-main": {
                "base_url": "https://user:pass@vault.example.test",
                "token_env_var": "VAULT_TOKEN",
            }
        },
        {
            "vault-main": {
                "base_url": "https://vault.example.test?token=raw",
                "token_env_var": "VAULT_TOKEN",
            }
        },
        {
            "vault-main": {
                "base_url": "https://vault.example.test",
                "token_env_var": "not a safe env",
            }
        },
        {
            "vault-main": {
                "base_url": "https://vault.example.test",
                "mount": "../secret",
                "token_env_var": "VAULT_TOKEN",
            }
        },
        {
            "vault-main": {
                "base_url": "https://vault.example.test",
                "mount": "secret/./team",
                "token_env_var": "VAULT_TOKEN",
            }
        },
        {
            "vault-main": {
                "type": "aws_secrets_manager",
                "base_url": "https://vault.example.test",
                "token_env_var": "VAULT_TOKEN",
            }
        },
        {
            "vault-main": {
                "base_url": "https://vault.example.test",
                "token_env_var": "VAULT_TOKEN",
                "unexpected": True,
            }
        },
    ],
)
def test_managed_secret_manager_adapters_fail_closed(
    tmp_path,
    monkeypatch,
    adapters_payload,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"credential_secret_manager_adapters": adapters_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match="credential_secret_manager_adapters"):
        get_settings()


@pytest.mark.parametrize(
    "allowed_urls",
    [
        "http://vault.example.test",
        "https://user:pass@vault.example.test",
        "https://vault.example.test?token=raw",
        "https://vault.example.test/TOKEN=raw-secret",
    ],
)
def test_managed_secret_manager_allowed_base_urls_fail_closed(
    tmp_path,
    monkeypatch,
    allowed_urls: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"credential_secret_manager_allowed_base_urls": allowed_urls}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match="credential_secret_manager_allowed_base_urls"):
        get_settings()


@pytest.mark.parametrize(
    ("records_payload", "error_match"),
    [
        ({"plugin_id": "not-a-list"}, "must be a list"),
        (
            [{"plugin_id": "bad-plugin", "unknown": True}],
            "Unknown managed plugin trust record field",
        ),
        (
            [
                {
                    "plugin_id": "missing-digest",
                    "status": "trusted",
                }
            ],
            "manifest_digest is invalid",
        ),
        (
            [
                {
                    "plugin_id": "duplicate-plugin",
                    "manifest_digest": "a" * 64,
                    "status": "trusted",
                },
                {
                    "plugin_id": "duplicate-plugin",
                    "manifest_digest": "b" * 64,
                    "status": "blocked",
                },
            ],
            "Duplicate managed plugin trust record",
        ),
        (
            [
                {
                    "plugin_id": "secret-plugin",
                    "manifest_digest": "a" * 64,
                    "status": "trusted",
                    "reason": "TOKEN=raw-secret",
                }
            ],
            "secret-shaped",
        ),
    ],
)
def test_managed_plugin_trust_records_fail_closed(
    tmp_path,
    monkeypatch,
    records_payload,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_plugin_trust_records": records_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


@pytest.mark.parametrize(
    ("records_payload", "error_match"),
    [
        ({"plugin_id": "not-a-list"}, "must be a list"),
        (
            [{"plugin_id": "bad.unknown", "unknown": True}],
            "Unknown managed plugin component field",
        ),
        (
            [
                {
                    "plugin_id": "bad plugin",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ],
            "plugin_id is invalid",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "unknown",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ],
            "type is invalid",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "manifest_digest": "not-a-digest",
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ],
            "manifest_digest is invalid",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "../scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ],
            "path is invalid",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": -1,
                }
            ],
            "size is invalid",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                    "status": "ready",
                }
            ],
            "status is invalid",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                },
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools\\scanner.json",
                    "component_digest": "c" * 64,
                    "component_size_bytes": 42,
                },
            ],
            "Duplicate managed plugin component id",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "DGENTIC_PLUGIN_ID": "managed-plugin-shadow",
                    "component_type": "tools",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ],
            "Duplicate managed plugin component field",
        ),
        (
            [
                {
                    "plugin_id": "managed-plugin",
                    "component_type": "tools",
                    "name": "TOKEN=component-secret",
                    "manifest_digest": "a" * 64,
                    "component_path": "tools/scanner.json",
                    "component_digest": "b" * 64,
                    "component_size_bytes": 42,
                }
            ],
            "secret-shaped",
        ),
    ],
)
def test_managed_plugin_component_records_fail_closed(
    tmp_path,
    monkeypatch,
    records_payload,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_plugin_component_records": records_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


@pytest.mark.parametrize(
    ("records_payload", "error_match"),
    [
        ({"id": "not-a-list"}, "must be a list"),
        (
            [
                {
                    "id": "managed.bad",
                    "source_type": "env",
                    "env_var": "DGENTIC_KEY",
                    "purpose": "provider",
                    "status": "active",
                    "unknown": True,
                }
            ],
            "Unknown managed credential reference field",
        ),
        (
            [
                {
                    "id": "managed.duplicate",
                    "source_type": "env",
                    "env_var": "DGENTIC_ONE",
                    "purpose": "provider",
                    "status": "active",
                },
                {
                    "id": "managed.duplicate",
                    "source_type": "env",
                    "env_var": "DGENTIC_TWO",
                    "purpose": "provider",
                    "status": "active",
                },
            ],
            "Duplicate managed credential reference id",
        ),
        (
            [
                {
                    "id": "managed.invalid-env",
                    "source_type": "env",
                    "env_var": "not a safe env",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "Managed credential reference is invalid",
        ),
        (
            [
                {
                    "id": "managed.mix",
                    "source_type": "env",
                    "env_var": "DGENTIC_KEY",
                    "adapter_id": "vault",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "Managed credential reference is invalid",
        ),
        (
            [
                {
                    "id": "managed.secret-label",
                    "source_type": "env",
                    "env_var": "DGENTIC_KEY",
                    "label": "TOKEN=raw-secret",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "secret-shaped",
        ),
        (
            [
                {
                    "id": "managed.secret-name",
                    "source_type": "external_process",
                    "adapter_id": "vault",
                    "secret_name": "TOKEN=raw-secret",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "secret-shaped",
        ),
        (
            [
                {
                    "id": "managed.local-vault",
                    "source_type": "local_vault",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "source_type is invalid",
        ),
        (
            [
                {
                    "id": "managed.vault-mix",
                    "source_type": "secret_manager",
                    "env_var": "DGENTIC_KEY",
                    "adapter_id": "vault-main",
                    "secret_name": "providers/openai",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "Managed credential reference is invalid",
        ),
        (
            [
                {
                    "id": "managed.vault-secret-name",
                    "source_type": "secret_manager",
                    "adapter_id": "vault-main",
                    "secret_name": "TOKEN=raw-secret",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "secret-shaped",
        ),
        (
            [
                {
                    "id": "managed.vault-bad-path",
                    "source_type": "secret_manager",
                    "adapter_id": "vault-main",
                    "secret_name": "/providers/openai",
                    "purpose": "provider",
                    "status": "active",
                }
            ],
            "Managed credential reference is invalid",
        ),
        (
            [
                {
                    "id": "managed.raw-secret",
                    "source_type": "env",
                    "env_var": "DGENTIC_KEY",
                    "purpose": "provider",
                    "status": "active",
                    "secret_value": "raw-secret",
                }
            ],
            "Unknown managed credential reference field",
        ),
    ],
)
def test_managed_credential_reference_records_fail_closed(
    tmp_path,
    monkeypatch,
    records_payload,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_credential_references": records_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


def test_managed_cli_policy_rules_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_CLI_POLICY_RULES",
        json.dumps(
            [
                {
                    "id": "env.rule",
                    "name": "Environment rule",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "permission_mode": "blocked",
                    "reason": "Environment rules are not managed.",
                }
            ]
        ),
    )

    assert managed_cli_policy_rules() == ()

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_cli_policy_rules": [
                    {
                        "id": "managed.deploy-review",
                        "name": "Managed deploy review",
                        "match_type": "contains",
                        "pattern": "deploy",
                        "permission_mode": "approval_required",
                        "reason": "Deploy commands require managed approval.",
                        "agent_roles": [" QA ", "developer", "qa"],
                        "priority": 15,
                    }
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    rules = managed_cli_policy_rules()

    assert json.loads(settings.managed_cli_policy_rules)[0]["id"] == "managed.deploy-review"
    assert fields["managed_cli_policy_rules"].source == "managed"
    assert view.managed_fields == ["managed_cli_policy_rules"]
    assert len(rules) == 1
    assert rules[0].id == "managed.deploy-review"
    assert rules[0].source == "managed"
    assert rules[0].agent_roles == ["developer", "qa"]
    assert rules[0].priority == 15


def test_managed_command_recipes_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_COMMAND_RECIPES",
        json.dumps(
            [
                {
                    "id": "env.recipe",
                    "name": "Environment recipe",
                    "command_template": "cmd /c echo env",
                }
            ]
        ),
    )

    assert managed_command_recipes() == ()

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_command_recipes": [
                    {
                        "id": "managed.echo",
                        "name": "Managed echo",
                        "description": "Deployment-owned command recipe.",
                        "command_template": "cmd /c echo {{message}}",
                        "parameters": [
                            {
                                "name": "message",
                                "description": "Message to print",
                                "default": "hello",
                            }
                        ],
                        "tags": ["managed", "smoke"],
                    }
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    recipes = managed_command_recipes()

    assert json.loads(settings.managed_command_recipes)[0]["id"] == "managed.echo"
    assert fields["managed_command_recipes"].source == "managed"
    assert view.managed_fields == ["managed_command_recipes"]
    assert len(recipes) == 1
    assert recipes[0].id == "managed.echo"
    assert recipes[0].source == "managed"
    assert recipes[0].parameters[0].default == "hello"
    assert recipes[0].tags == ["managed", "smoke"]


@pytest.mark.parametrize(
    ("recipes_payload", "error_match"),
    [
        ({"id": "not-a-list"}, "must be a list"),
        ([{"id": "bad.unknown", "unknown": True}], "Unknown managed command recipe field"),
        (
            [
                {
                    "name": "Missing id",
                    "command_template": "cmd /c echo missing-id",
                }
            ],
            "id is invalid",
        ),
        (
            [
                {
                    "id": "duplicate.recipe",
                    "name": "First duplicate",
                    "command_template": "cmd /c echo one",
                },
                {
                    "id": "duplicate.recipe",
                    "name": "Second duplicate",
                    "command_template": "cmd /c echo two",
                },
            ],
            "Duplicate managed command recipe id",
        ),
        (
            [
                {
                    "id": "duplicate.normalized",
                    "name": "First normalized duplicate",
                    "command_template": "cmd /c echo one",
                },
                {
                    "id": " duplicate.normalized ",
                    "name": "Second normalized duplicate",
                    "command_template": "cmd /c echo two",
                },
            ],
            "Duplicate managed command recipe id",
        ),
        (
            [
                {
                    "id": "duplicate.field",
                    "DGENTIC_ID": "duplicate.field.shadow",
                    "name": "Duplicate normalized field",
                    "command_template": "cmd /c echo duplicate",
                }
            ],
            "Duplicate managed command recipe field",
        ),
        (
            [
                {
                    "id": "secret.recipe",
                    "name": "Secret-shaped recipe",
                    "command_template": "cmd /c echo TOKEN=raw-secret",
                }
            ],
            "secret-shaped",
        ),
        (
            [
                {
                    "id": "bad.template",
                    "name": "Bad template",
                    "command_template": "cmd /c echo {{missing}}",
                    "parameters": [{"name": "declared"}],
                }
            ],
            "Managed command recipe is invalid",
        ),
    ],
)
def test_managed_command_recipes_fail_closed(
    tmp_path,
    monkeypatch,
    recipes_payload,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_command_recipes": recipes_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


@pytest.mark.parametrize(
    ("rules_payload", "error_match"),
    [
        ({"id": "not-a-list"}, "must be a list"),
        ([{"id": "bad.unknown", "unknown": True}], "Unknown managed CLI policy rule field"),
        (
            [
                {
                    "id": "missing-required-fields",
                    "name": "Missing required fields",
                }
            ],
            "Managed CLI policy rule is invalid",
        ),
        (
            [
                {
                    "id": "duplicate.rule",
                    "name": "First duplicate",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "permission_mode": "blocked",
                    "reason": "First duplicate rule.",
                },
                {
                    "id": "duplicate.rule",
                    "name": "Second duplicate",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "permission_mode": "blocked",
                    "reason": "Second duplicate rule.",
                },
            ],
            "Duplicate managed CLI policy rule id",
        ),
        (
            [
                {
                    "id": "secret.rule",
                    "name": "Secret-shaped rule",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "permission_mode": "blocked",
                    "reason": "TOKEN=raw-secret",
                }
            ],
            "secret-shaped",
        ),
    ],
)
def test_managed_cli_policy_rules_fail_closed(
    tmp_path,
    monkeypatch,
    rules_payload,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_cli_policy_rules": rules_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


def test_managed_hook_policy_rules_apply_only_from_managed_settings(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv(
        "DGENTIC_MANAGED_HOOK_POLICY_RULES",
        json.dumps(
            [
                {
                    "id": "env.hook",
                    "name": "Environment hook",
                    "surface": "command",
                    "action": "execute",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "effect": "blocked",
                    "reason": "Environment hooks are not managed.",
                }
            ]
        ),
    )

    assert managed_hook_policy_rules() == ()

    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {
            "settings": {
                "managed_hook_policy_rules": [
                    {
                        "id": "managed.deploy-hook",
                        "name": "Managed deploy hook",
                        "surface": "command",
                        "action": " EXECUTE ",
                        "match_type": "contains",
                        "pattern": "deploy",
                        "effect": "approval_required",
                        "reason": "Deploy hooks require managed approval.",
                        "agent_roles": [" QA ", "developer", "qa"],
                        "priority": 15,
                    }
                ]
            }
        },
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)
    get_settings.cache_clear()

    settings = get_settings()
    view = get_effective_settings_view()
    fields = {item.name: item for item in view.settings}
    rules = managed_hook_policy_rules()

    assert json.loads(settings.managed_hook_policy_rules)[0]["id"] == "managed.deploy-hook"
    assert fields["managed_hook_policy_rules"].source == "managed"
    assert view.managed_fields == ["managed_hook_policy_rules"]
    assert len(rules) == 1
    assert rules[0].id == "managed.deploy-hook"
    assert rules[0].source == "managed"
    assert rules[0].action == "execute"
    assert rules[0].agent_roles == ["developer", "qa"]
    assert rules[0].priority == 15


@pytest.mark.parametrize(
    ("rules_payload", "error_match"),
    [
        ({"id": "not-a-list"}, "must be a list"),
        ([{"id": "bad.unknown", "unknown": True}], "Unknown managed hook policy rule field"),
        (
            [
                {
                    "id": "missing-required-fields",
                    "name": "Missing required fields",
                }
            ],
            "Managed hook policy rule is invalid",
        ),
        (
            [
                {
                    "id": "duplicate.hook",
                    "name": "First duplicate",
                    "surface": "command",
                    "action": "execute",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "effect": "blocked",
                    "reason": "First duplicate rule.",
                },
                {
                    "id": "duplicate.hook",
                    "name": "Second duplicate",
                    "surface": "command",
                    "action": "execute",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "effect": "blocked",
                    "reason": "Second duplicate rule.",
                },
            ],
            "Duplicate managed hook policy rule id",
        ),
        (
            [
                {
                    "id": "secret.pattern",
                    "name": "Secret pattern",
                    "surface": "command",
                    "action": "execute",
                    "match_type": "contains",
                    "pattern": "TOKEN=raw-secret",
                    "effect": "blocked",
                    "reason": "Reject secret-shaped patterns.",
                }
            ],
            "stable non-secret",
        ),
        (
            [
                {
                    "id": "network.query",
                    "name": "Network query",
                    "surface": "network",
                    "action": "request",
                    "match_type": "contains",
                    "pattern": "https://api.example.test/private?page=1",
                    "effect": "blocked",
                    "reason": "Reject query strings.",
                }
            ],
            "query strings",
        ),
        (
            [
                {
                    "id": "secret.reason",
                    "name": "Secret-shaped reason",
                    "surface": "command",
                    "action": "execute",
                    "match_type": "contains",
                    "pattern": "deploy",
                    "effect": "blocked",
                    "reason": "TOKEN=raw-secret",
                }
            ],
            "secret-shaped",
        ),
    ],
)
def test_managed_hook_policy_rules_fail_closed(
    tmp_path,
    monkeypatch,
    rules_payload,
    error_match: str,
) -> None:
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(tmp_path))
    managed_path, _raw_payload = _write_managed_settings(
        tmp_path,
        {"settings": {"managed_hook_policy_rules": rules_payload}},
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", managed_path)

    with pytest.raises(ManagedSettingsError, match=error_match):
        get_settings()


@pytest.mark.parametrize(
    ("payload", "error_match"),
    [
        ("not-json", "valid JSON"),
        ({"unexpected": {}}, "settings object"),
        ({"settings": {"root_dir": "/tmp/other"}}, "not supported"),
        ({"settings": {"unknown_setting": True}}, "Unknown managed settings field"),
        ({"settings": {"managed_settings_file": "nested.json"}}, "reserved"),
        ({"settings": {"app_name": "TOKEN=raw-secret"}}, "secret-shaped"),
        (
            {"settings": {"managed_policy_locks": ["unknown-surface"]}},
            "Unknown managed policy lock surface",
        ),
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
