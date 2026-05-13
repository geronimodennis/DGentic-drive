import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from dgentic.redaction import REDACTED_SECRET_MARKER, redact_metadata, redact_sensitive_values

SettingsSource = Literal["default", "environment", "managed", "derived"]

_MANAGED_SETTINGS_RESERVED_FIELDS = frozenset({"managed_settings_file"})
_MANAGED_SETTINGS_ALLOWED_FIELDS = frozenset(
    {
        "app_name",
        "auth_enabled",
        "credential_process_adapters",
        "credential_process_max_output_bytes",
        "credential_process_timeout_seconds",
        "external_openai_compatible_api_key_env",
        "external_openai_compatible_base_url",
        "external_openai_compatible_credential_ref",
        "external_openai_compatible_models",
        "lm_studio_base_url",
        "managed_cli_policy_rules",
        "managed_hook_policy_rules",
        "managed_policy_locks",
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
    }
)
_MANAGED_SETTINGS_MAX_BYTES = 256 * 1024
_JSON_STRING_SETTINGS_FIELDS = frozenset(
    {
        "credential_process_adapters",
        "managed_cli_policy_rules",
        "managed_hook_policy_rules",
        "managed_policy_locks",
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
_MANAGED_RULE_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC)
MANAGED_POLICY_LOCK_SURFACES = frozenset(
    {
        "cli_policy",
        "command_recipes",
        "hook_policy",
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
        "credential_vault_key",
        "external_openai_compatible_api_key_env",
        "external_openai_compatible_credential_ref",
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
    managed_hook_policy_rules: str = ""
    managed_policy_locks: str = ""
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
    credential_vault_key: str = ""
    credential_process_adapters: str = ""
    credential_process_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    credential_process_max_output_bytes: int = Field(default=4096, ge=1, le=65536)

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
class SettingsSourceMetadata:
    sources: dict[str, SettingsSource]
    managed_settings_file: str | None = None
    managed_settings_digest: str | None = None
    managed_fields: tuple[str, ...] = ()


_LAST_SETTINGS_SOURCE_METADATA = SettingsSourceMetadata(sources={})


@lru_cache
def get_settings() -> Settings:
    global _LAST_SETTINGS_SOURCE_METADATA

    settings = Settings()
    effective_settings, metadata = _apply_managed_settings(settings)
    _LAST_SETTINGS_SOURCE_METADATA = metadata
    return effective_settings


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


def managed_hook_policy_rules():
    metadata = get_settings_source_metadata()
    if metadata.sources.get("managed_hook_policy_rules") != "managed":
        return tuple()
    return _parse_managed_hook_policy_rules(get_settings().managed_hook_policy_rules)


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
        if key == "managed_cli_policy_rules":
            _parse_managed_cli_policy_rules(value)
        if key == "managed_hook_policy_rules":
            _parse_managed_hook_policy_rules(value)
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
