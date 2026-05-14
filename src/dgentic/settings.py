import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from dgentic.redaction import REDACTED_SECRET_MARKER, redact_metadata, redact_sensitive_values

SettingsSource = Literal["default", "environment", "managed", "runtime", "derived"]

_MANAGED_SETTINGS_RESERVED_FIELDS = frozenset({"managed_settings_file"})
_MANAGED_SETTINGS_ALLOWED_FIELDS = frozenset(
    {
        "app_name",
        "auth_enabled",
        "credential_process_adapters",
        "credential_process_max_output_bytes",
        "credential_process_timeout_seconds",
        "credential_secret_manager_adapters",
        "credential_secret_manager_allowed_base_urls",
        "external_openai_compatible_api_key_env",
        "external_openai_compatible_base_url",
        "external_openai_compatible_credential_ref",
        "external_openai_compatible_models",
        "managed_credential_references",
        "lm_studio_base_url",
        "managed_cli_policy_rules",
        "managed_command_recipes",
        "managed_hook_policy_rules",
        "managed_network_domain_policy_rules",
        "managed_policy_locks",
        "managed_plugin_component_records",
        "managed_plugin_trust_records",
        "max_filesystem_bytes",
        "network_domain_policy",
        "ollama_base_url",
        "provider_allowed_base_urls",
        "provider_circuit_breaker_cooldown_seconds",
        "provider_circuit_breaker_failure_threshold",
        "provider_pricing_catalog",
        "provider_retry_backoff_multiplier",
        "provider_retry_initial_delay_seconds",
        "provider_retry_max_attempts",
        "provider_retry_max_delay_seconds",
        "provider_role_routing",
        "web_retrieval_max_response_bytes",
        "web_retrieval_timeout_seconds",
    }
)
_MANAGED_SETTINGS_MAX_BYTES = 256 * 1024
_JSON_STRING_SETTINGS_FIELDS = frozenset(
    {
        "credential_process_adapters",
        "credential_secret_manager_adapters",
        "managed_credential_references",
        "managed_cli_policy_rules",
        "managed_command_recipes",
        "managed_hook_policy_rules",
        "managed_network_domain_policy_rules",
        "managed_policy_locks",
        "managed_plugin_component_records",
        "managed_plugin_trust_records",
        "network_domain_policy",
        "provider_pricing_catalog",
        "provider_role_routing",
    }
)
_MANAGED_CLI_POLICY_RULE_MAX_COUNT = 100
_MANAGED_CLI_POLICY_RULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_MANAGED_CLI_POLICY_RULE_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "name",
        "match_type",
        "pattern",
        "permission_mode",
        "reason",
        "agent_roles",
        "enabled",
        "priority",
    }
)
_MANAGED_COMMAND_RECIPE_MAX_COUNT = 100
_MANAGED_COMMAND_RECIPE_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "name",
        "description",
        "command_template",
        "cwd",
        "timeout_seconds",
        "parameters",
        "tags",
        "enabled",
    }
)
_MANAGED_CREDENTIAL_REFERENCE_MAX_COUNT = 100
_MANAGED_CREDENTIAL_REFERENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_MANAGED_CREDENTIAL_REFERENCE_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "source_type",
        "env_var",
        "adapter_id",
        "secret_name",
        "label",
        "purpose",
        "status",
    }
)
_MANAGED_HOOK_POLICY_RULE_MAX_COUNT = 100
_MANAGED_HOOK_POLICY_RULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_MANAGED_HOOK_POLICY_RULE_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "name",
        "surface",
        "action",
        "match_type",
        "pattern",
        "effect",
        "reason",
        "agent_roles",
        "enabled",
        "priority",
    }
)
_MANAGED_NETWORK_DOMAIN_POLICY_RULE_MAX_COUNT = 100
_MANAGED_NETWORK_DOMAIN_POLICY_RULE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_MANAGED_NETWORK_DOMAIN_PATTERN = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
_MANAGED_NETWORK_DOMAIN_POLICY_RULE_ALLOWED_FIELDS = frozenset(
    {
        "id",
        "domain",
        "mode",
        "reason",
        "enabled",
        "priority",
    }
)
_MANAGED_NETWORK_POLICY_MODES = frozenset({"allow", "deny", "approval_required", "audit"})
_MANAGED_NETWORK_RULE_REASON_MAX_CHARS = 500
_MANAGED_PLUGIN_TRUST_RECORD_MAX_COUNT = 100
_MANAGED_PLUGIN_COMPONENT_RECORD_MAX_COUNT = 200
_MANAGED_PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_MANAGED_PLUGIN_DIGEST_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_MANAGED_PLUGIN_COMPONENT_TYPES = frozenset({"agent_blueprints", "skills", "tools", "docs"})
_MANAGED_PLUGIN_TRUST_ALLOWED_FIELDS = frozenset(
    {
        "plugin_id",
        "manifest_digest",
        "status",
        "reason",
        "decided_by",
    }
)
_MANAGED_PLUGIN_COMPONENT_ALLOWED_FIELDS = frozenset(
    {
        "plugin_id",
        "component_type",
        "name",
        "manifest_digest",
        "component_path",
        "component_digest",
        "component_size_bytes",
        "status",
    }
)
_MANAGED_RULE_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC)
MANAGED_POLICY_LOCK_SURFACES = frozenset(
    {
        "cli_policy",
        "command_recipes",
        "hook_policy",
        "network_policy",
        "plugin_command_recipes",
        "plugin_components",
        "plugin_hook_policies",
        "plugin_trust",
    }
)
_SECRET_SETTINGS_FIELDS = frozenset(
    {
        "approval_digest_key",
        "auth_tokens",
        "credential_process_adapters",
        "credential_secret_manager_adapters",
        "credential_secret_manager_allowed_base_urls",
        "credential_vault_key",
        "external_openai_compatible_api_key_env",
        "external_openai_compatible_credential_ref",
        "managed_credential_references",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DGENTIC_",
        extra="ignore",
    )

    app_name: str = "DGentic"
    environment: str = "development"
    root_dir: Path = Field(default=Path("."))
    data_dir: Path = Field(default=Path(".dgentic"))
    database_url: str | None = None
    autopilot_enabled: bool = False
    auth_enabled: bool | None = None
    auth_tokens: str = ""
    approval_digest_key: str = ""
    managed_settings_file: str = ""
    managed_cli_policy_rules: str = ""
    managed_command_recipes: str = ""
    managed_hook_policy_rules: str = ""
    managed_network_domain_policy_rules: str = ""
    managed_policy_locks: str = ""
    managed_plugin_component_records: str = ""
    managed_plugin_trust_records: str = ""
    max_filesystem_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    ollama_base_url: str = "http://127.0.0.1:11434"
    lm_studio_base_url: str = "http://127.0.0.1:1234"
    provider_allowed_base_urls: str = ""
    network_domain_policy: str = ""
    provider_retry_max_attempts: int = Field(default=3, ge=1, le=10)
    provider_retry_initial_delay_seconds: float = Field(default=0.2, ge=0.0, le=30.0)
    provider_retry_max_delay_seconds: float = Field(default=2.0, ge=0.0, le=120.0)
    provider_retry_backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    provider_circuit_breaker_failure_threshold: int = Field(default=3, ge=1, le=100)
    provider_circuit_breaker_cooldown_seconds: float = Field(default=30.0, ge=0.0, le=3600.0)
    provider_pricing_catalog: str = ""
    provider_role_routing: str = ""
    external_openai_compatible_base_url: str = ""
    external_openai_compatible_api_key_env: str = ""
    external_openai_compatible_credential_ref: str = ""
    external_openai_compatible_models: str = ""
    managed_credential_references: str = ""
    credential_vault_key: str = ""
    credential_process_adapters: str = ""
    credential_secret_manager_adapters: str = ""
    credential_secret_manager_allowed_base_urls: str = ""
    credential_process_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    credential_process_max_output_bytes: int = Field(default=4096, ge=1, le=65536)
    web_retrieval_timeout_seconds: float = Field(default=10.0, ge=0.1, le=30.0)
    web_retrieval_max_response_bytes: int = Field(
        default=256 * 1024,
        ge=1,
        le=2 * 1024 * 1024,
    )

    @property
    def effective_auth_enabled(self) -> bool:
        if self.auth_enabled is not None:
            return self.auth_enabled
        return self.environment.lower() in {"production", "staging"}

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url

        data_dir = self.data_dir
        if not data_dir.is_absolute():
            data_dir = self.root_dir / data_dir

        database_path = data_dir / "dgentic.db"
        return f"sqlite:///{database_path.as_posix()}"


class ManagedSettingsError(RuntimeError):
    """Raised when an opt-in managed settings source cannot be applied safely."""


class EffectiveSettingValue(BaseModel):
    name: str
    source: SettingsSource
    value: Any
    redacted: bool = False


class EffectiveSettingsView(BaseModel):
    managed_settings_enabled: bool
    managed_settings_file: str | None = None
    managed_settings_digest: str | None = None
    managed_fields: list[str] = Field(default_factory=list)
    settings: list[EffectiveSettingValue] = Field(default_factory=list)


@dataclass(frozen=True)
class ManagedPluginTrustRecord:
    plugin_id: str
    manifest_digest: str
    status: Literal["trusted", "blocked"]
    reason: str = ""
    decided_by: str = "managed"


@dataclass(frozen=True)
class ManagedNetworkDomainPolicyRuleRecord:
    id: str
    domain: str
    mode: Literal["allow", "deny", "approval_required", "audit"]
    reason: str = ""
    enabled: bool = True
    priority: int = 100
    source: Literal["managed"] = "managed"


@dataclass(frozen=True)
class SettingsSourceMetadata:
    sources: dict[str, SettingsSource]
    managed_settings_file: str | None = None
    managed_settings_digest: str | None = None
    managed_fields: tuple[str, ...] = ()


_LAST_SETTINGS_SOURCE_METADATA = SettingsSourceMetadata(sources={})
_RUNTIME_SETTINGS_LOCK = Lock()
_RUNTIME_SETTINGS_OVERRIDES: dict[str, Any] = {}
_RUNTIME_ROOT_SWITCH_LOCK = Lock()


@lru_cache
def get_settings() -> Settings:
    global _LAST_SETTINGS_SOURCE_METADATA

    settings = Settings()
    effective_settings, metadata = _apply_managed_settings(settings)
    effective_settings, metadata = _apply_runtime_settings_overrides(
        effective_settings,
        metadata,
    )
    _LAST_SETTINGS_SOURCE_METADATA = metadata
    return effective_settings


def activate_runtime_root_dir(root_dir: Path) -> Settings:
    """Switch the in-process runtime root while keeping DGentic state anchored."""

    if root_dir.is_symlink():
        raise ValueError("Runtime rootDir must not be a symlink.")
    try:
        resolved_root_dir = root_dir.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Runtime rootDir must exist.") from exc
    if not resolved_root_dir.is_dir():
        raise ValueError("Runtime rootDir must be a directory.")

    current_settings = get_settings()
    stable_data_dir = current_settings.data_dir
    if not stable_data_dir.is_absolute():
        current_root_dir = current_settings.root_dir
        if not current_root_dir.is_absolute():
            current_root_dir = current_root_dir.resolve()
        stable_data_dir = (current_root_dir / stable_data_dir).resolve()

    with _RUNTIME_SETTINGS_LOCK:
        _RUNTIME_SETTINGS_OVERRIDES["root_dir"] = resolved_root_dir
        _RUNTIME_SETTINGS_OVERRIDES["data_dir"] = stable_data_dir
    get_settings.cache_clear()
    return get_settings()


def clear_runtime_settings_overrides() -> None:
    """Clear in-process runtime settings overrides for tests and process reset hooks."""

    with _RUNTIME_SETTINGS_LOCK:
        _RUNTIME_SETTINGS_OVERRIDES.clear()
    get_settings.cache_clear()


@contextmanager
def runtime_root_switch_barrier() -> Iterator[None]:
    """Serialize root-sensitive API work with active runtime root switching."""

    with _RUNTIME_ROOT_SWITCH_LOCK:
        yield


def get_settings_source_metadata() -> SettingsSourceMetadata:
    get_settings()
    return _LAST_SETTINGS_SOURCE_METADATA


def get_effective_settings_view() -> EffectiveSettingsView:
    settings = get_settings()
    metadata = get_settings_source_metadata()
    values: list[EffectiveSettingValue] = []

    for name in sorted(Settings.model_fields):
        value, redacted = _redacted_setting_value(name, getattr(settings, name))
        values.append(
            EffectiveSettingValue(
                name=name,
                source=metadata.sources.get(name, "default"),
                value=value,
                redacted=redacted,
            )
        )

    values.append(
        EffectiveSettingValue(
            name="effective_auth_enabled",
            source="derived",
            value=settings.effective_auth_enabled,
        )
    )

    return EffectiveSettingsView(
        managed_settings_enabled=metadata.managed_settings_file is not None,
        managed_settings_file=metadata.managed_settings_file,
        managed_settings_digest=metadata.managed_settings_digest,
        managed_fields=list(metadata.managed_fields),
        settings=values,
    )


def managed_policy_locks() -> frozenset[str]:
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_policy_locks") != "managed":
        return frozenset()
    return _parse_managed_policy_locks(get_settings().managed_policy_locks)


def managed_cli_policy_rules():
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_cli_policy_rules") != "managed":
        return tuple()
    return _parse_managed_cli_policy_rules(get_settings().managed_cli_policy_rules)


def managed_command_recipes():
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_command_recipes") != "managed":
        return tuple()
    return _parse_managed_command_recipes(get_settings().managed_command_recipes)


def managed_credential_references():
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_credential_references") != "managed":
        return tuple()
    return _parse_managed_credential_references(get_settings().managed_credential_references)


def managed_hook_policy_rules():
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_hook_policy_rules") != "managed":
        return tuple()
    return _parse_managed_hook_policy_rules(get_settings().managed_hook_policy_rules)


def managed_network_domain_policy_rules(settings: Settings | None = None):
    if settings is None:
        metadata = get_settings_source_metadata()
        active_settings = get_settings()
    else:
        metadata = _LAST_SETTINGS_SOURCE_METADATA
        if metadata.sources.get("managed_network_domain_policy_rules") != "managed":
            return tuple()
        active_settings = get_settings()
        if settings is not active_settings:
            return tuple()
    if metadata.sources.get("managed_network_domain_policy_rules") != "managed":
        return tuple()
    return _parse_managed_network_domain_policy_rules(
        active_settings.managed_network_domain_policy_rules
    )


def managed_plugin_trust_records() -> tuple[ManagedPluginTrustRecord, ...]:
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_plugin_trust_records") != "managed":
        return tuple()
    return _parse_managed_plugin_trust_records(get_settings().managed_plugin_trust_records)


def managed_plugin_component_records():
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_plugin_component_records") != "managed":
        return tuple()
    return _parse_managed_plugin_component_records(get_settings().managed_plugin_component_records)


def require_managed_policy_surface_mutable(surface: str) -> None:
    normalized = _normalize_managed_policy_lock_surface(surface)
    if normalized in managed_policy_locks():
        raise PermissionError(f"Policy surface '{normalized}' is locked by managed settings.")


def _apply_managed_settings(settings: Settings) -> tuple[Settings, SettingsSourceMetadata]:
    sources = _settings_source_map()
    managed_path = _managed_settings_path(settings)
    if managed_path is None:
        return settings, SettingsSourceMetadata(sources=sources)

    raw_payload = _read_managed_settings_payload(managed_path)
    managed_values = _managed_settings_values(raw_payload)
    _validate_managed_settings_ceiling(settings, managed_values)
    settings_payload = settings.model_dump()
    settings_payload.update(managed_values)

    try:
        effective_settings = Settings.model_validate(settings_payload)
    except ValidationError as exc:
        raise ManagedSettingsError("Managed settings values are invalid.") from exc

    for field_name in managed_values:
        sources[field_name] = "managed"

    return effective_settings, SettingsSourceMetadata(
        sources=sources,
        managed_settings_file=redact_sensitive_values(str(managed_path)),
        managed_settings_digest=sha256(raw_payload.encode("utf-8")).hexdigest(),
        managed_fields=tuple(sorted(managed_values)),
    )


def _apply_runtime_settings_overrides(
    settings: Settings,
    metadata: SettingsSourceMetadata,
) -> tuple[Settings, SettingsSourceMetadata]:
    with _RUNTIME_SETTINGS_LOCK:
        overrides = dict(_RUNTIME_SETTINGS_OVERRIDES)
    if not overrides:
        return settings, metadata

    try:
        effective_settings = Settings.model_validate({**settings.model_dump(), **overrides})
    except ValidationError as exc:
        raise ManagedSettingsError("Runtime settings override values are invalid.") from exc

    sources = dict(metadata.sources)
    for field_name in overrides:
        sources[field_name] = "runtime"

    return effective_settings, SettingsSourceMetadata(
        sources=sources,
        managed_settings_file=metadata.managed_settings_file,
        managed_settings_digest=metadata.managed_settings_digest,
        managed_fields=metadata.managed_fields,
    )


def _managed_settings_path(settings: Settings) -> Path | None:
    configured_path = settings.managed_settings_file.strip()
    if not configured_path:
        return None

    managed_path = Path(configured_path).expanduser()
    if managed_path.is_absolute():
        return managed_path

    root_dir = settings.root_dir
    if not root_dir.is_absolute():
        root_dir = root_dir.resolve()
    return root_dir / managed_path


def _read_managed_settings_payload(path: Path) -> str:
    try:
        if not path.exists():
            raise ManagedSettingsError(f"Managed settings file does not exist: {path}")
        if not path.is_file():
            raise ManagedSettingsError(f"Managed settings path is not a file: {path}")
        if path.stat().st_size > _MANAGED_SETTINGS_MAX_BYTES:
            raise ManagedSettingsError("Managed settings file is too large.")
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManagedSettingsError("Managed settings file could not be read.") from exc


def _managed_settings_values(raw_payload: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("Managed settings file must contain valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ManagedSettingsError("Managed settings file must contain a JSON object.")

    raw_settings = payload.get("settings")
    if not isinstance(raw_settings, dict):
        raise ManagedSettingsError("Managed settings file must contain a settings object.")

    values: dict[str, Any] = {}
    field_names = set(Settings.model_fields)
    for raw_key, raw_value in raw_settings.items():
        key = _normalize_managed_settings_key(str(raw_key))
        if key in _MANAGED_SETTINGS_RESERVED_FIELDS:
            raise ManagedSettingsError(f"Managed settings field is reserved: {key}")
        if key not in field_names:
            raise ManagedSettingsError(f"Unknown managed settings field: {key}")
        if key not in _MANAGED_SETTINGS_ALLOWED_FIELDS:
            raise ManagedSettingsError(f"Managed settings field is not supported: {key}")
        if key in values:
            raise ManagedSettingsError(f"Duplicate managed settings field: {key}")
        values[key] = _coerce_managed_settings_value(key, raw_value)

    return values


def _validate_managed_settings_ceiling(settings: Settings, values: dict[str, Any]) -> None:
    if values.get("auth_enabled") is False and settings.effective_auth_enabled:
        raise ManagedSettingsError("Managed settings cannot disable already-effective auth.")

    for key, value in values.items():
        if key == "credential_secret_manager_adapters":
            from dgentic.credentials import (
                CredentialReferenceError,
                credential_secret_manager_adapters,
            )

            try:
                credential_secret_manager_adapters(
                    Settings.model_validate({**settings.model_dump(), key: value})
                )
            except CredentialReferenceError as exc:
                raise ManagedSettingsError(
                    "credential_secret_manager_adapters is invalid."
                ) from exc
            continue
        if key == "credential_secret_manager_allowed_base_urls":
            from dgentic.credentials import (
                CredentialReferenceError,
                credential_secret_manager_allowed_base_urls,
            )

            try:
                credential_secret_manager_allowed_base_urls(
                    Settings.model_validate({**settings.model_dump(), key: value})
                )
            except CredentialReferenceError as exc:
                raise ManagedSettingsError(
                    "credential_secret_manager_allowed_base_urls is invalid."
                ) from exc
        if key == "managed_cli_policy_rules":
            _parse_managed_cli_policy_rules(value)
        if key == "managed_command_recipes":
            _parse_managed_command_recipes(value)
        if key == "managed_credential_references":
            _parse_managed_credential_references(value)
            continue
        if key == "managed_hook_policy_rules":
            _parse_managed_hook_policy_rules(value)
        if key == "managed_network_domain_policy_rules":
            _parse_managed_network_domain_policy_rules(value)
        if key == "managed_plugin_component_records":
            _parse_managed_plugin_component_records(value)
        if key == "managed_plugin_trust_records":
            _parse_managed_plugin_trust_records(value)
        if key == "managed_policy_locks":
            _parse_managed_policy_locks(value)
        if _managed_value_contains_secret_shape(key, value):
            raise ManagedSettingsError(f"Managed settings field contains secret-shaped text: {key}")


def _normalize_managed_settings_key(value: str) -> str:
    key = value.strip()
    if key.upper().startswith("DGENTIC_"):
        key = key[8:]
    return key.lower()


def _managed_value_contains_secret_shape(key: str, value: Any) -> bool:
    if value is None:
        return False
    candidate = value
    if key in _JSON_STRING_SETTINGS_FIELDS and isinstance(value, str):
        try:
            candidate = json.loads(value)
        except json.JSONDecodeError:
            candidate = value
    return redact_metadata(candidate) != candidate


def _coerce_managed_settings_value(key: str, value: Any) -> Any:
    if key in _JSON_STRING_SETTINGS_FIELDS and isinstance(value, dict | list):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return value


def _parse_managed_policy_locks(raw_value: str) -> frozenset[str]:
    raw_text = raw_value.strip()
    if not raw_text:
        return frozenset()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw_text.split(",") if item.strip()]
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_policy_locks must be a list of policy surfaces.")

    locks: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise ManagedSettingsError("managed_policy_locks entries must be strings.")
        surface = _normalize_managed_policy_lock_surface(item)
        if surface not in MANAGED_POLICY_LOCK_SURFACES:
            raise ManagedSettingsError(f"Unknown managed policy lock surface: {surface}")
        if surface not in locks:
            locks.append(surface)
    return frozenset(locks)


def _parse_managed_cli_policy_rules(raw_value: str):
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("managed_cli_policy_rules must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_cli_policy_rules must be a list.")
    if len(parsed) > _MANAGED_CLI_POLICY_RULE_MAX_COUNT:
        raise ManagedSettingsError("managed_cli_policy_rules declares too many rules.")

    from dgentic.schemas import CommandPolicyRule, CommandPolicyRuleRequest

    rules: list[CommandPolicyRule] = []
    seen_ids: set[str] = set()
    for raw_rule in parsed:
        if not isinstance(raw_rule, dict):
            raise ManagedSettingsError("managed_cli_policy_rules entries must be objects.")
        normalized_rule = {
            _normalize_managed_settings_key(str(key)): value for key, value in raw_rule.items()
        }
        unknown_fields = sorted(set(normalized_rule) - _MANAGED_CLI_POLICY_RULE_ALLOWED_FIELDS)
        if unknown_fields:
            raise ManagedSettingsError(
                f"Unknown managed CLI policy rule field: {unknown_fields[0]}"
            )
        rule_id = normalized_rule.pop("id", None)
        if not isinstance(rule_id, str) or not _MANAGED_CLI_POLICY_RULE_ID_RE.fullmatch(rule_id):
            raise ManagedSettingsError("Managed CLI policy rule id is invalid.")
        if redact_sensitive_values(rule_id) != rule_id:
            raise ManagedSettingsError("Managed CLI policy rule id is invalid.")
        if rule_id in seen_ids:
            raise ManagedSettingsError(f"Duplicate managed CLI policy rule id: {rule_id}")
        seen_ids.add(rule_id)
        try:
            request = CommandPolicyRuleRequest.model_validate(normalized_rule)
        except ValueError as exc:
            raise ManagedSettingsError("Managed CLI policy rule is invalid.") from exc
        rules.append(
            CommandPolicyRule(
                id=rule_id,
                name=request.name,
                match_type=request.match_type,
                pattern=request.pattern,
                permission_mode=request.permission_mode,
                reason=request.reason,
                agent_roles=_normalize_managed_cli_policy_agent_roles(request.agent_roles),
                enabled=request.enabled,
                priority=request.priority,
                source="managed",
                created_at=_MANAGED_RULE_TIMESTAMP,
                updated_at=_MANAGED_RULE_TIMESTAMP,
            )
        )
    return tuple(rules)


def _normalize_managed_cli_policy_agent_roles(agent_roles: list[str]) -> list[str]:
    return sorted({role.strip().lower() for role in agent_roles if role.strip()})


def _parse_managed_command_recipes(raw_value: str):
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("managed_command_recipes must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_command_recipes must be a list.")
    if len(parsed) > _MANAGED_COMMAND_RECIPE_MAX_COUNT:
        raise ManagedSettingsError("managed_command_recipes declares too many recipes.")

    from dgentic.command_recipes import CommandRecipe, CommandRecipeRequest

    recipes: list[CommandRecipe] = []
    seen_ids: set[str] = set()
    for raw_recipe in parsed:
        if not isinstance(raw_recipe, dict):
            raise ManagedSettingsError("managed_command_recipes entries must be objects.")
        normalized_recipe: dict[str, Any] = {}
        for raw_key, value in raw_recipe.items():
            key = _normalize_managed_settings_key(str(raw_key))
            if key in normalized_recipe:
                raise ManagedSettingsError(f"Duplicate managed command recipe field: {key}")
            normalized_recipe[key] = value
        unknown_fields = sorted(set(normalized_recipe) - _MANAGED_COMMAND_RECIPE_ALLOWED_FIELDS)
        if unknown_fields:
            raise ManagedSettingsError(f"Unknown managed command recipe field: {unknown_fields[0]}")
        if redact_metadata(normalized_recipe) != normalized_recipe:
            raise ManagedSettingsError("Managed command recipe contains secret-shaped text.")
        raw_recipe_id = normalized_recipe.get("id")
        if not isinstance(raw_recipe_id, str):
            raise ManagedSettingsError("Managed command recipe id is invalid.")
        if redact_sensitive_values(raw_recipe_id) != raw_recipe_id:
            raise ManagedSettingsError("Managed command recipe id is invalid.")
        try:
            request = CommandRecipeRequest.model_validate(normalized_recipe)
        except ValueError as exc:
            raise ManagedSettingsError("Managed command recipe is invalid.") from exc
        if request.id is None:
            raise ManagedSettingsError("Managed command recipe id is required.")
        if request.id in seen_ids:
            raise ManagedSettingsError(f"Duplicate managed command recipe id: {request.id}")
        seen_ids.add(request.id)
        recipes.append(
            CommandRecipe(
                id=request.id,
                name=redact_sensitive_values(request.name),
                description=redact_sensitive_values(request.description),
                command_template=request.command_template,
                cwd=request.cwd,
                timeout_seconds=request.timeout_seconds,
                parameters=request.parameters,
                tags=request.tags,
                enabled=request.enabled,
                usage_count=0,
                source="managed",
                created_at=_MANAGED_RULE_TIMESTAMP,
                updated_at=_MANAGED_RULE_TIMESTAMP,
            )
        )
    return tuple(recipes)


def _parse_managed_credential_references(raw_value: str):
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("managed_credential_references must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_credential_references must be a list.")
    if len(parsed) > _MANAGED_CREDENTIAL_REFERENCE_MAX_COUNT:
        raise ManagedSettingsError("managed_credential_references declares too many records.")

    from dgentic.credentials import CredentialReferenceRecord

    records: list[CredentialReferenceRecord] = []
    seen_ids: set[str] = set()
    required_fields = {"id", "source_type", "purpose", "status"}
    for raw_record in parsed:
        if not isinstance(raw_record, dict):
            raise ManagedSettingsError("managed_credential_references entries must be objects.")
        normalized_record: dict[str, Any] = {}
        for raw_key, value in raw_record.items():
            key = _normalize_managed_settings_key(str(raw_key))
            if key in normalized_record:
                raise ManagedSettingsError(f"Duplicate managed credential reference field: {key}")
            normalized_record[key] = value
        unknown_fields = sorted(
            set(normalized_record) - _MANAGED_CREDENTIAL_REFERENCE_ALLOWED_FIELDS
        )
        if unknown_fields:
            raise ManagedSettingsError(
                f"Unknown managed credential reference field: {unknown_fields[0]}"
            )
        missing_fields = sorted(required_fields - set(normalized_record))
        if missing_fields:
            raise ManagedSettingsError(
                f"Managed credential reference field is required: {missing_fields[0]}"
            )

        record_id = normalized_record.get("id")
        if not isinstance(record_id, str) or not _MANAGED_CREDENTIAL_REFERENCE_ID_RE.fullmatch(
            record_id
        ):
            raise ManagedSettingsError("Managed credential reference id is invalid.")
        if redact_sensitive_values(record_id) != record_id:
            raise ManagedSettingsError("Managed credential reference id is invalid.")
        if record_id in seen_ids:
            raise ManagedSettingsError(f"Duplicate managed credential reference id: {record_id}")
        seen_ids.add(record_id)

        source_type = normalized_record.get("source_type")
        if source_type not in {"env", "external_process", "secret_manager"}:
            raise ManagedSettingsError("Managed credential reference source_type is invalid.")

        _validate_managed_credential_reference_metadata(normalized_record)

        try:
            record = CredentialReferenceRecord.model_validate(
                {
                    **normalized_record,
                    "source": "managed",
                    "created_at": _MANAGED_RULE_TIMESTAMP,
                    "updated_at": _MANAGED_RULE_TIMESTAMP,
                    "revoked_at": None,
                    "encrypted_secret": "",
                }
            )
        except ValueError as exc:
            raise ManagedSettingsError("Managed credential reference is invalid.") from exc
        records.append(record)
    return tuple(records)


def _validate_managed_credential_reference_metadata(record: dict[str, Any]) -> None:
    for field_name in ("id", "env_var", "adapter_id", "secret_name", "label"):
        value = record.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ManagedSettingsError("Managed credential reference metadata is invalid.")
        if redact_sensitive_values(value.strip()) != value.strip():
            raise ManagedSettingsError("Managed credential reference contains secret-shaped text.")


def _parse_managed_network_domain_policy_rules(
    raw_value: str,
) -> tuple[ManagedNetworkDomainPolicyRuleRecord, ...]:
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError(
            "managed_network_domain_policy_rules must be valid JSON."
        ) from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_network_domain_policy_rules must be a list.")
    if len(parsed) > _MANAGED_NETWORK_DOMAIN_POLICY_RULE_MAX_COUNT:
        raise ManagedSettingsError("managed_network_domain_policy_rules declares too many rules.")

    rules: list[ManagedNetworkDomainPolicyRuleRecord] = []
    seen_ids: set[str] = set()
    seen_domains: set[str] = set()
    for raw_rule in parsed:
        if not isinstance(raw_rule, dict):
            raise ManagedSettingsError(
                "managed_network_domain_policy_rules entries must be objects."
            )
        normalized_rule: dict[str, Any] = {}
        for raw_key, value in raw_rule.items():
            key = _normalize_managed_settings_key(str(raw_key))
            if key in normalized_rule:
                raise ManagedSettingsError(
                    f"Duplicate managed network domain policy rule field: {key}"
                )
            normalized_rule[key] = value
        unknown_fields = sorted(
            set(normalized_rule) - _MANAGED_NETWORK_DOMAIN_POLICY_RULE_ALLOWED_FIELDS
        )
        if unknown_fields:
            raise ManagedSettingsError(
                f"Unknown managed network domain policy rule field: {unknown_fields[0]}"
            )

        rule_id = _normalize_managed_network_rule_id(normalized_rule.get("id"))
        if rule_id in seen_ids:
            raise ManagedSettingsError(
                f"Duplicate managed network domain policy rule id: {rule_id}"
            )
        seen_ids.add(rule_id)

        domain = _normalize_managed_network_rule_domain(normalized_rule.get("domain"))
        if domain in seen_domains:
            raise ManagedSettingsError(
                f"Duplicate managed network domain policy rule domain: {domain}"
            )
        seen_domains.add(domain)

        rules.append(
            ManagedNetworkDomainPolicyRuleRecord(
                id=rule_id,
                domain=domain,
                mode=_normalize_managed_network_rule_mode(normalized_rule.get("mode")),
                reason=_normalize_managed_network_rule_reason(normalized_rule.get("reason", "")),
                enabled=_normalize_managed_network_rule_enabled(
                    normalized_rule.get("enabled", True)
                ),
                priority=_normalize_managed_network_rule_priority(
                    normalized_rule.get("priority", 100)
                ),
            )
        )
    return tuple(sorted(rules, key=_managed_network_rule_sort_key))


def _normalize_managed_network_rule_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ManagedSettingsError("Managed network domain policy rule id is invalid.")
    rule_id = value.strip()
    if (
        not rule_id
        or not _MANAGED_NETWORK_DOMAIN_POLICY_RULE_ID_RE.fullmatch(rule_id)
        or redact_sensitive_values(rule_id) != rule_id
    ):
        raise ManagedSettingsError("Managed network domain policy rule id is invalid.")
    return rule_id


def _normalize_managed_network_rule_domain(value: Any) -> str:
    if not isinstance(value, str):
        raise ManagedSettingsError("Managed network domain policy rule domain must be a string.")
    domain = value.strip().lower().rstrip(".")
    if (
        not domain
        or "/" in domain
        or ":" in domain
        or ".." in domain
        or not _MANAGED_NETWORK_DOMAIN_PATTERN.fullmatch(domain)
        or redact_sensitive_values(domain) != domain
    ):
        raise ManagedSettingsError("Managed network domain policy rule domain is not valid.")
    return domain


def _normalize_managed_network_rule_mode(value: Any):
    if not isinstance(value, str):
        raise ManagedSettingsError("Managed network domain policy rule mode must be a string.")
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in _MANAGED_NETWORK_POLICY_MODES:
        raise ManagedSettingsError("Managed network domain policy rule mode is not supported.")
    return normalized


def _normalize_managed_network_rule_reason(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ManagedSettingsError("Managed network domain policy rule reason must be a string.")
    reason = value.strip()
    if len(reason) > _MANAGED_NETWORK_RULE_REASON_MAX_CHARS:
        raise ManagedSettingsError("Managed network domain policy rule reason is too long.")
    if redact_sensitive_values(reason) != reason:
        raise ManagedSettingsError(
            "Managed network domain policy rule reason contains secret-shaped text."
        )
    return reason


def _normalize_managed_network_rule_enabled(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ManagedSettingsError("Managed network domain policy rule enabled is invalid.")
    return value


def _normalize_managed_network_rule_priority(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManagedSettingsError("Managed network domain policy rule priority is invalid.")
    if value < 0 or value > 10_000:
        raise ManagedSettingsError("Managed network domain policy rule priority is invalid.")
    return value


def _managed_network_rule_sort_key(
    rule: ManagedNetworkDomainPolicyRuleRecord,
) -> tuple[int, bool, int, str]:
    specificity_domain = rule.domain[2:] if rule.domain.startswith("*.") else rule.domain
    return (rule.priority, rule.domain.startswith("*."), -len(specificity_domain), rule.id)


def _parse_managed_hook_policy_rules(raw_value: str):
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("managed_hook_policy_rules must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_hook_policy_rules must be a list.")
    if len(parsed) > _MANAGED_HOOK_POLICY_RULE_MAX_COUNT:
        raise ManagedSettingsError("managed_hook_policy_rules declares too many rules.")

    from dgentic.schemas import HookPolicyMatchType, HookPolicyRule, HookPolicyRuleRequest

    rules: list[HookPolicyRule] = []
    seen_ids: set[str] = set()
    for raw_rule in parsed:
        if not isinstance(raw_rule, dict):
            raise ManagedSettingsError("managed_hook_policy_rules entries must be objects.")
        normalized_rule = {
            _normalize_managed_settings_key(str(key)): value for key, value in raw_rule.items()
        }
        unknown_fields = sorted(set(normalized_rule) - _MANAGED_HOOK_POLICY_RULE_ALLOWED_FIELDS)
        if unknown_fields:
            raise ManagedSettingsError(
                f"Unknown managed hook policy rule field: {unknown_fields[0]}"
            )
        rule_id = normalized_rule.pop("id", None)
        if not isinstance(rule_id, str) or not _MANAGED_HOOK_POLICY_RULE_ID_RE.fullmatch(rule_id):
            raise ManagedSettingsError("Managed hook policy rule id is invalid.")
        if redact_sensitive_values(rule_id) != rule_id:
            raise ManagedSettingsError("Managed hook policy rule id is invalid.")
        if rule_id in seen_ids:
            raise ManagedSettingsError(f"Duplicate managed hook policy rule id: {rule_id}")
        seen_ids.add(rule_id)
        try:
            request = HookPolicyRuleRequest.model_validate(normalized_rule)
        except ValueError as exc:
            raise ManagedSettingsError("Managed hook policy rule is invalid.") from exc

        pattern = request.pattern.strip()
        if request.match_type == HookPolicyMatchType.any:
            stored_pattern = redact_sensitive_values(pattern)
        else:
            if redact_sensitive_values(pattern) != pattern:
                raise ManagedSettingsError(
                    "Managed hook policy patterns must use stable non-secret match values."
                )
            if request.surface == "network" and ("?" in pattern or "#" in pattern):
                raise ManagedSettingsError(
                    "Managed network hook policy patterns must not include query strings "
                    "or fragments."
                )
            stored_pattern = pattern
        rules.append(
            HookPolicyRule(
                id=rule_id,
                name=redact_sensitive_values(request.name),
                surface=request.surface,
                action=_normalize_managed_hook_policy_action(request.action),
                match_type=request.match_type,
                pattern=stored_pattern,
                effect=request.effect,
                reason=redact_sensitive_values(request.reason),
                agent_roles=_normalize_managed_hook_policy_agent_roles(request.agent_roles),
                enabled=request.enabled,
                priority=request.priority,
                source="managed",
                created_at=_MANAGED_RULE_TIMESTAMP,
                updated_at=_MANAGED_RULE_TIMESTAMP,
            )
        )
    return tuple(rules)


def _parse_managed_plugin_trust_records(
    raw_value: str,
) -> tuple[ManagedPluginTrustRecord, ...]:
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("managed_plugin_trust_records must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_plugin_trust_records must be a list.")
    if len(parsed) > _MANAGED_PLUGIN_TRUST_RECORD_MAX_COUNT:
        raise ManagedSettingsError("managed_plugin_trust_records declares too many records.")

    records: list[ManagedPluginTrustRecord] = []
    seen_plugin_ids: set[str] = set()
    for raw_record in parsed:
        if not isinstance(raw_record, dict):
            raise ManagedSettingsError("managed_plugin_trust_records entries must be objects.")
        normalized_record = {
            _normalize_managed_settings_key(str(key)): value for key, value in raw_record.items()
        }
        unknown_fields = sorted(set(normalized_record) - _MANAGED_PLUGIN_TRUST_ALLOWED_FIELDS)
        if unknown_fields:
            raise ManagedSettingsError(
                f"Unknown managed plugin trust record field: {unknown_fields[0]}"
            )
        plugin_id = normalized_record.get("plugin_id")
        manifest_digest = normalized_record.get("manifest_digest")
        status = normalized_record.get("status")
        reason = normalized_record.get("reason", "")
        decided_by = normalized_record.get("decided_by", "managed")
        if not isinstance(plugin_id, str) or not _MANAGED_PLUGIN_ID_RE.fullmatch(plugin_id):
            raise ManagedSettingsError("Managed plugin trust record plugin_id is invalid.")
        if redact_sensitive_values(plugin_id) != plugin_id:
            raise ManagedSettingsError("Managed plugin trust record plugin_id is invalid.")
        if plugin_id in seen_plugin_ids:
            raise ManagedSettingsError(f"Duplicate managed plugin trust record: {plugin_id}")
        seen_plugin_ids.add(plugin_id)
        if not isinstance(manifest_digest, str) or not _MANAGED_PLUGIN_DIGEST_RE.fullmatch(
            manifest_digest
        ):
            raise ManagedSettingsError("Managed plugin trust record manifest_digest is invalid.")
        if status not in {"trusted", "blocked"}:
            raise ManagedSettingsError("Managed plugin trust record status is invalid.")
        if not isinstance(reason, str) or not isinstance(decided_by, str):
            raise ManagedSettingsError("Managed plugin trust record metadata is invalid.")
        records.append(
            ManagedPluginTrustRecord(
                plugin_id=plugin_id,
                manifest_digest=manifest_digest.lower(),
                status=status,
                reason=redact_sensitive_values(reason.strip()),
                decided_by=redact_sensitive_values(decided_by.strip()) or "managed",
            )
        )
    return tuple(records)


def _parse_managed_plugin_component_records(raw_value: str):
    raw_text = raw_value.strip()
    if not raw_text:
        return tuple()
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManagedSettingsError("managed_plugin_component_records must be valid JSON.") from exc
    if not isinstance(parsed, list):
        raise ManagedSettingsError("managed_plugin_component_records must be a list.")
    if len(parsed) > _MANAGED_PLUGIN_COMPONENT_RECORD_MAX_COUNT:
        raise ManagedSettingsError("managed_plugin_component_records declares too many records.")

    from dgentic.plugins import (
        PluginReferenceComponentRecord,
        _normalize_component_path,
        _plugin_reference_component_id,
    )

    records: list[PluginReferenceComponentRecord] = []
    seen_component_ids: set[str] = set()
    for raw_record in parsed:
        if not isinstance(raw_record, dict):
            raise ManagedSettingsError("managed_plugin_component_records entries must be objects.")
        normalized_record: dict[str, Any] = {}
        for raw_key, value in raw_record.items():
            key = _normalize_managed_settings_key(str(raw_key))
            if key in normalized_record:
                raise ManagedSettingsError(f"Duplicate managed plugin component field: {key}")
            normalized_record[key] = value
        unknown_fields = sorted(set(normalized_record) - _MANAGED_PLUGIN_COMPONENT_ALLOWED_FIELDS)
        if unknown_fields:
            raise ManagedSettingsError(
                f"Unknown managed plugin component field: {unknown_fields[0]}"
            )
        if redact_metadata(normalized_record) != normalized_record:
            raise ManagedSettingsError(
                "Managed plugin component record contains secret-shaped text."
            )

        plugin_id = normalized_record.get("plugin_id")
        component_type = normalized_record.get("component_type")
        manifest_digest = normalized_record.get("manifest_digest")
        component_path = normalized_record.get("component_path")
        component_digest = normalized_record.get("component_digest")
        component_size_bytes = normalized_record.get("component_size_bytes")
        status = normalized_record.get("status", "installed")
        name = normalized_record.get("name", "")

        if not isinstance(plugin_id, str) or not _MANAGED_PLUGIN_ID_RE.fullmatch(plugin_id):
            raise ManagedSettingsError("Managed plugin component plugin_id is invalid.")
        if redact_sensitive_values(plugin_id) != plugin_id:
            raise ManagedSettingsError("Managed plugin component plugin_id is invalid.")
        if component_type not in _MANAGED_PLUGIN_COMPONENT_TYPES:
            raise ManagedSettingsError("Managed plugin component type is invalid.")
        if not isinstance(manifest_digest, str) or not _MANAGED_PLUGIN_DIGEST_RE.fullmatch(
            manifest_digest
        ):
            raise ManagedSettingsError("Managed plugin component manifest_digest is invalid.")
        if not isinstance(component_digest, str) or not _MANAGED_PLUGIN_DIGEST_RE.fullmatch(
            component_digest
        ):
            raise ManagedSettingsError("Managed plugin component component_digest is invalid.")
        if not isinstance(component_path, str):
            raise ManagedSettingsError("Managed plugin component path is invalid.")
        try:
            normalized_path = _normalize_component_path(component_path)
        except ValueError as exc:
            raise ManagedSettingsError("Managed plugin component path is invalid.") from exc
        if not isinstance(component_size_bytes, int) or component_size_bytes < 0:
            raise ManagedSettingsError("Managed plugin component size is invalid.")
        if status not in {"installed", "disabled"}:
            raise ManagedSettingsError("Managed plugin component status is invalid.")
        if not isinstance(name, str):
            raise ManagedSettingsError("Managed plugin component name is invalid.")

        component_id = _plugin_reference_component_id(
            plugin_id,
            component_type,
            normalized_path,
        )
        if component_id in seen_component_ids:
            raise ManagedSettingsError(f"Duplicate managed plugin component id: {component_id}")
        seen_component_ids.add(component_id)
        records.append(
            PluginReferenceComponentRecord(
                component_id=component_id,
                plugin_id=plugin_id,
                component_type=component_type,
                name=redact_sensitive_values(name.strip()),
                manifest_digest=manifest_digest.lower(),
                component_path=normalized_path,
                component_digest=component_digest.lower(),
                component_size_bytes=component_size_bytes,
                status=status,
                installed_by="managed",
                source="managed",
                created_at=_MANAGED_RULE_TIMESTAMP,
                updated_at=_MANAGED_RULE_TIMESTAMP,
            )
        )
    return tuple(records)


def _normalize_managed_hook_policy_action(action: str) -> str:
    return action.strip().lower() or "*"


def _normalize_managed_hook_policy_agent_roles(agent_roles: list[str]) -> list[str]:
    return sorted({role.strip().lower() for role in agent_roles if role.strip()})


def _normalize_managed_policy_lock_surface(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _settings_source_map() -> dict[str, SettingsSource]:
    environment_fields = _environment_settings_fields()
    return {
        name: "environment" if name in environment_fields else "default"
        for name in Settings.model_fields
    }


def _environment_settings_fields() -> set[str]:
    configured_names = set(os.environ) | _dotenv_keys()
    fields: set[str] = set()
    for name in Settings.model_fields:
        env_name = f"DGENTIC_{name.upper()}"
        if env_name in configured_names:
            fields.add(name)
    return fields


def _dotenv_keys() -> set[str]:
    dotenv_path = Path(".env")
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return set()

    keys: set[str] = set()
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key.startswith("export "):
            key = key[7:].strip()
        if key:
            keys.add(key)
    return keys


def _redacted_setting_value(name: str, value: Any) -> tuple[Any, bool]:
    if name in _SECRET_SETTINGS_FIELDS:
        return REDACTED_SECRET_MARKER, True
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        redacted_value = redact_sensitive_values(value)
        return redacted_value, redacted_value != value
    if isinstance(value, list):
        redacted_items = [_redacted_arbitrary_value(item) for item in value]
        return redacted_items, redacted_items != value
    if isinstance(value, dict):
        redacted_map = {key: _redacted_arbitrary_value(item) for key, item in value.items()}
        return redacted_map, redacted_map != value
    return value, False


def _redacted_arbitrary_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return redact_sensitive_values(value)
    if isinstance(value, list):
        return [_redacted_arbitrary_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redacted_arbitrary_value(item) for key, item in value.items()}
    return value
