import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from stat import S_ISREG
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dgentic.command_recipes import (
    CommandRecipeRequest,
    PluginCommandRecipeInstallRequest,
    disable_plugin_command_recipes,
    install_plugin_command_recipe,
)
from dgentic.events import event_log
from dgentic.hook_policy import (
    PluginHookPolicyInstallRequest,
    disable_plugin_hook_policy_rules,
    install_plugin_hook_policy_rule,
    validate_hook_policy_rule_request,
)
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import HookPolicyRuleRequest, LogEventType
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

PLUGIN_MANIFEST_NAME = "dgentic-plugin.json"
PLUGIN_MANIFEST_MAX_BYTES = 64 * 1024
PLUGIN_COMPONENT_MAX_BYTES = 64 * 1024
PLUGIN_HOOK_POLICY_MAX_RULES = 50
PLUGIN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"
PluginTrustDecision = Literal["trusted", "blocked"]
PluginTrustStatus = Literal["trusted", "blocked", "untrusted", "stale"]
PluginActivationStatus = Literal["ready", "installed", "disabled"]
PluginReferenceComponentType = Literal["agent_blueprints", "skills", "tools", "docs"]


@dataclass(frozen=True)
class _LoadedPluginReferenceComponent:
    component_id: str
    component_type: PluginReferenceComponentType
    name: str
    component_path: str
    component_digest: str
    component_size_bytes: int


class PluginCommandRecipeComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)

    @field_validator("path")
    @classmethod
    def path_must_be_relative_safe_text(cls, value: str) -> str:
        return _normalize_component_path(value)


class PluginHookPolicyComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)

    @field_validator("path")
    @classmethod
    def path_must_be_relative_safe_text(cls, value: str) -> str:
        return _normalize_component_path(value)


class PluginReferenceComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    name: str = Field(default="", max_length=120)

    @field_validator("path")
    @classmethod
    def path_must_be_relative_safe_text(cls, value: str) -> str:
        return _normalize_component_path(value)

    @field_validator("name")
    @classmethod
    def name_must_be_safe_text(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())[:120]


class PluginComponentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_recipes: list[str] = Field(default_factory=list, max_length=50)
    agent_blueprints: list[str] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=50)
    hook_policies: list[str] = Field(default_factory=list, max_length=50)
    tools: list[str] = Field(default_factory=list, max_length=50)
    docs: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("*")
    @classmethod
    def component_names_must_be_safe(cls, values: list[str]) -> list[str]:
        safe_values: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = redact_sensitive_values(value.strip())[:120]
            if normalized and normalized not in safe_values:
                safe_values.append(normalized)
        return safe_values


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_id: str = Field(min_length=1, max_length=80, pattern=PLUGIN_ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=200)
    components: PluginComponentSummary = Field(default_factory=PluginComponentSummary)
    command_recipes: list[PluginCommandRecipeComponent] = Field(default_factory=list, max_length=50)
    hook_policies: list[PluginHookPolicyComponent] = Field(default_factory=list, max_length=50)
    agent_blueprints: list[PluginReferenceComponent] = Field(default_factory=list, max_length=50)
    skills: list[PluginReferenceComponent] = Field(default_factory=list, max_length=50)
    tools: list[PluginReferenceComponent] = Field(default_factory=list, max_length=50)
    docs: list[PluginReferenceComponent] = Field(default_factory=list, max_length=50)

    @field_validator("plugin_id", "name", "version", "description", "source")
    @classmethod
    def text_fields_must_be_redacted(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())


class PluginTrustRecord(BaseModel):
    plugin_id: str = Field(min_length=1, max_length=80, pattern=PLUGIN_ID_PATTERN)
    manifest_digest: str = Field(min_length=64, max_length=64)
    status: PluginTrustDecision
    reason: str = Field(default="", max_length=500)
    decided_by: str = Field(default="system", max_length=120)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("reason", "decided_by")
    @classmethod
    def text_fields_must_be_redacted(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())

    @field_validator("created_at", "updated_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class PluginTrustRequest(BaseModel):
    status: PluginTrustDecision
    reason: str = Field(default="", max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_be_redacted(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())


class PluginDiscoveryView(BaseModel):
    plugin_id: str
    name: str
    version: str
    description: str = ""
    source: str = ""
    components: PluginComponentSummary
    command_recipes: list[PluginCommandRecipeComponent] = Field(default_factory=list)
    hook_policies: list[PluginHookPolicyComponent] = Field(default_factory=list)
    agent_blueprints: list[PluginReferenceComponent] = Field(default_factory=list)
    skills: list[PluginReferenceComponent] = Field(default_factory=list)
    tools: list[PluginReferenceComponent] = Field(default_factory=list)
    docs: list[PluginReferenceComponent] = Field(default_factory=list)
    manifest_path: str
    manifest_digest: str
    manifest_size_bytes: int = Field(ge=0)
    trust_status: PluginTrustStatus = "untrusted"
    trust_reason: str = ""
    trusted_manifest_digest: str = ""
    decided_by: str = ""
    trust_updated_at: datetime | None = None


class PluginDiscoveryError(BaseModel):
    plugin_id: str
    manifest_path: str
    reason: str


class PluginDiscoveryResponse(BaseModel):
    plugins: list[PluginDiscoveryView] = Field(default_factory=list)
    errors: list[PluginDiscoveryError] = Field(default_factory=list)


class PluginCommandRecipeActivationView(BaseModel):
    recipe_id: str
    name: str
    component_path: str
    component_digest: str
    manifest_digest: str
    status: PluginActivationStatus


class PluginCommandRecipeActivationResponse(BaseModel):
    plugin_id: str
    manifest_digest: str = ""
    command_recipes: list[PluginCommandRecipeActivationView] = Field(default_factory=list)


class PluginHookPolicyActivationView(BaseModel):
    rule_id: str
    name: str
    component_path: str
    component_digest: str
    manifest_digest: str
    status: PluginActivationStatus


class PluginHookPolicyActivationResponse(BaseModel):
    plugin_id: str
    manifest_digest: str = ""
    hook_policies: list[PluginHookPolicyActivationView] = Field(default_factory=list)


class PluginReferenceComponentPreviewView(BaseModel):
    component_id: str
    component_type: PluginReferenceComponentType
    name: str
    component_path: str
    component_digest: str
    component_size_bytes: int = Field(ge=0)
    manifest_digest: str
    status: Literal["ready"] = "ready"


class PluginReferenceComponentPreviewResponse(BaseModel):
    plugin_id: str
    manifest_digest: str = ""
    components: list[PluginReferenceComponentPreviewView] = Field(default_factory=list)


class PluginReferenceComponentRecord(BaseModel):
    component_id: str = Field(min_length=1, max_length=140)
    plugin_id: str = Field(min_length=1, max_length=80, pattern=PLUGIN_ID_PATTERN)
    component_type: PluginReferenceComponentType
    name: str = Field(default="", max_length=120)
    manifest_digest: str = Field(min_length=64, max_length=64)
    component_path: str = Field(min_length=1, max_length=300)
    component_digest: str = Field(min_length=64, max_length=64)
    component_size_bytes: int = Field(ge=0)
    status: Literal["installed", "disabled"] = "installed"
    installed_by: str = Field(default="system", max_length=120)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("name", "installed_by")
    @classmethod
    def text_fields_must_be_redacted(cls, value: str) -> str:
        return redact_sensitive_values(value.strip())

    @field_validator("component_path")
    @classmethod
    def component_path_must_be_relative_safe_text(cls, value: str) -> str:
        return _normalize_component_path(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class PluginReferenceComponentActivationView(BaseModel):
    component_id: str
    component_type: PluginReferenceComponentType
    name: str
    component_path: str
    component_digest: str
    component_size_bytes: int = Field(ge=0)
    manifest_digest: str
    status: Literal["installed", "disabled"]


class PluginReferenceComponentActivationResponse(BaseModel):
    plugin_id: str
    manifest_digest: str = ""
    components: list[PluginReferenceComponentActivationView] = Field(default_factory=list)


_plugin_trust = JsonCollection("plugin-trust", PluginTrustRecord, key_field="plugin_id")
_plugin_reference_components = JsonCollection(
    "plugin-components",
    PluginReferenceComponentRecord,
    key_field="component_id",
)


def discover_plugins() -> PluginDiscoveryResponse:
    plugins_dir = _plugins_dir()
    if plugins_dir.is_symlink():
        return PluginDiscoveryResponse(
            errors=[
                PluginDiscoveryError(
                    plugin_id="",
                    manifest_path="plugins",
                    reason="Plugin directory is invalid.",
                )
            ]
        )
    if not plugins_dir.exists():
        return PluginDiscoveryResponse()
    if not plugins_dir.is_dir():
        return PluginDiscoveryResponse(
            errors=[
                PluginDiscoveryError(
                    plugin_id="",
                    manifest_path="plugins",
                    reason="Plugin directory is invalid.",
                )
            ]
        )

    plugins: list[PluginDiscoveryView] = []
    errors: list[PluginDiscoveryError] = []
    for plugin_dir in sorted(plugins_dir.iterdir(), key=lambda path: path.name.lower()):
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / PLUGIN_MANIFEST_NAME
        try:
            plugins.append(_plugin_view_from_manifest_path(manifest_path))
        except ValueError as exc:
            errors.append(
                PluginDiscoveryError(
                    plugin_id=redact_sensitive_values(plugin_dir.name.strip())[:80],
                    manifest_path=_relative_plugin_path(manifest_path),
                    reason=str(exc),
                )
            )
    return PluginDiscoveryResponse(plugins=plugins, errors=errors)


def get_plugin(plugin_id: str) -> PluginDiscoveryView:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    plugin = next(
        (item for item in discover_plugins().plugins if item.plugin_id == normalized_plugin_id),
        None,
    )
    if plugin is None:
        raise KeyError(f"Plugin not found: {normalized_plugin_id}")
    return plugin


def update_plugin_trust(
    plugin_id: str,
    request: PluginTrustRequest,
    *,
    actor: str | None = None,
) -> PluginDiscoveryView:
    plugin = get_plugin(plugin_id)
    now = datetime.now(UTC)
    record = PluginTrustRecord(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        status=request.status,
        reason=request.reason,
        decided_by=actor or "system",
        created_at=now,
        updated_at=now,
    )

    def upsert(
        items: list[PluginTrustRecord],
    ) -> tuple[list[PluginTrustRecord], PluginTrustRecord]:
        updated_items: list[PluginTrustRecord] = []
        existing_created_at = now
        replaced = False
        for item in items:
            if item.plugin_id == record.plugin_id:
                existing_created_at = item.created_at
                updated_items.append(record.model_copy(update={"created_at": existing_created_at}))
                replaced = True
            else:
                updated_items.append(item)
        if not replaced:
            updated_items.append(record)
        saved = record.model_copy(update={"created_at": existing_created_at})
        return updated_items, saved

    saved = _plugin_trust.transact(upsert)
    _record_plugin_trust_event(saved, actor=actor)
    return get_plugin(plugin.plugin_id)


def preview_plugin_command_recipe_activation(
    plugin_id: str,
) -> PluginCommandRecipeActivationResponse:
    plugin = _trusted_plugin_for_activation(plugin_id)
    components = _load_plugin_command_recipe_components(plugin)
    return PluginCommandRecipeActivationResponse(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        command_recipes=[
            PluginCommandRecipeActivationView(
                recipe_id=recipe.id or "",
                name=recipe.name,
                component_path=component_path,
                component_digest=component_digest,
                manifest_digest=plugin.manifest_digest,
                status="ready",
            )
            for recipe, component_path, component_digest in components
        ],
    )


def install_plugin_command_recipes(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> PluginCommandRecipeActivationResponse:
    plugin = _trusted_plugin_for_activation(plugin_id)
    components = _load_plugin_command_recipe_components(plugin)
    installed: list[PluginCommandRecipeActivationView] = []
    for recipe, component_path, component_digest in components:
        saved = install_plugin_command_recipe(
            PluginCommandRecipeInstallRequest(
                recipe=recipe,
                plugin_id=plugin.plugin_id,
                manifest_digest=plugin.manifest_digest,
                component_path=component_path,
                component_digest=component_digest,
            ),
            actor=actor,
        )
        installed.append(
            PluginCommandRecipeActivationView(
                recipe_id=saved.id,
                name=saved.name,
                component_path=component_path,
                component_digest=component_digest,
                manifest_digest=plugin.manifest_digest,
                status="installed",
            )
        )
    _record_plugin_activation_event(
        "Installed plugin command recipes.",
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        actor=actor,
        command_recipes=installed,
    )
    return PluginCommandRecipeActivationResponse(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        command_recipes=installed,
    )


def disable_plugin_command_recipe_activation(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> PluginCommandRecipeActivationResponse:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    disabled_recipes = disable_plugin_command_recipes(normalized_plugin_id, actor=actor)
    disabled = [
        PluginCommandRecipeActivationView(
            recipe_id=recipe.id,
            name=recipe.name,
            component_path=recipe.source_plugin_component_path or "",
            component_digest=recipe.source_plugin_component_digest or "",
            manifest_digest=recipe.source_plugin_manifest_digest or "",
            status="disabled",
        )
        for recipe in disabled_recipes
    ]
    _record_plugin_activation_event(
        "Disabled plugin command recipes.",
        plugin_id=normalized_plugin_id,
        manifest_digest="",
        actor=actor,
        command_recipes=disabled,
    )
    return PluginCommandRecipeActivationResponse(
        plugin_id=normalized_plugin_id,
        command_recipes=disabled,
    )


def preview_plugin_hook_policy_activation(
    plugin_id: str,
) -> PluginHookPolicyActivationResponse:
    plugin = _trusted_plugin_for_activation(plugin_id)
    components = _load_plugin_hook_policy_components(plugin)
    return PluginHookPolicyActivationResponse(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        hook_policies=[
            PluginHookPolicyActivationView(
                rule_id=rule_id,
                name=rule.name,
                component_path=component_path,
                component_digest=component_digest,
                manifest_digest=plugin.manifest_digest,
                status="ready",
            )
            for rule_id, rule, component_path, component_digest in components
        ],
    )


def install_plugin_hook_policies(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> PluginHookPolicyActivationResponse:
    plugin = _trusted_plugin_for_activation(plugin_id)
    components = _load_plugin_hook_policy_components(plugin)
    installed: list[PluginHookPolicyActivationView] = []
    for rule_id, rule, component_path, component_digest in components:
        saved = install_plugin_hook_policy_rule(
            PluginHookPolicyInstallRequest(
                rule_id=rule_id,
                rule=rule,
                plugin_id=plugin.plugin_id,
                manifest_digest=plugin.manifest_digest,
                component_path=component_path,
                component_digest=component_digest,
            ),
            actor=actor,
        )
        installed.append(
            PluginHookPolicyActivationView(
                rule_id=saved.id,
                name=saved.name,
                component_path=component_path,
                component_digest=component_digest,
                manifest_digest=plugin.manifest_digest,
                status="installed",
            )
        )
    _record_plugin_hook_policy_activation_event(
        "Installed plugin hook policy rules.",
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        actor=actor,
        hook_policies=installed,
    )
    return PluginHookPolicyActivationResponse(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        hook_policies=installed,
    )


def disable_plugin_hook_policy_activation(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> PluginHookPolicyActivationResponse:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    disabled_rules = disable_plugin_hook_policy_rules(normalized_plugin_id, actor=actor)
    disabled = [
        PluginHookPolicyActivationView(
            rule_id=rule.id,
            name=rule.name,
            component_path=rule.source_plugin_component_path or "",
            component_digest=rule.source_plugin_component_digest or "",
            manifest_digest=rule.source_plugin_manifest_digest or "",
            status="disabled",
        )
        for rule in disabled_rules
    ]
    _record_plugin_hook_policy_activation_event(
        "Disabled plugin hook policy rules.",
        plugin_id=normalized_plugin_id,
        manifest_digest="",
        actor=actor,
        hook_policies=disabled,
    )
    return PluginHookPolicyActivationResponse(
        plugin_id=normalized_plugin_id,
        hook_policies=disabled,
    )


def preview_plugin_reference_components(
    plugin_id: str,
) -> PluginReferenceComponentPreviewResponse:
    plugin = _trusted_plugin_for_activation(plugin_id)
    components = _load_plugin_reference_components(plugin)
    return PluginReferenceComponentPreviewResponse(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        components=[
            _preview_reference_component_view(component, plugin.manifest_digest)
            for component in components
        ],
    )


def install_plugin_reference_components(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> PluginReferenceComponentActivationResponse:
    plugin = _trusted_plugin_for_activation(plugin_id)
    components = _load_plugin_reference_components(plugin)
    now = datetime.now(UTC)
    records = [
        PluginReferenceComponentRecord(
            component_id=component.component_id,
            plugin_id=plugin.plugin_id,
            component_type=component.component_type,
            name=component.name,
            manifest_digest=plugin.manifest_digest,
            component_path=component.component_path,
            component_digest=component.component_digest,
            component_size_bytes=component.component_size_bytes,
            status="installed",
            installed_by=actor or "system",
            created_at=now,
            updated_at=now,
        )
        for component in components
    ]

    def upsert(
        items: list[PluginReferenceComponentRecord],
    ) -> tuple[list[PluginReferenceComponentRecord], list[PluginReferenceComponentRecord]]:
        records_by_id = {record.component_id: record for record in records}
        saved_by_id: dict[str, PluginReferenceComponentRecord] = {}
        updated_items: list[PluginReferenceComponentRecord] = []
        for item in items:
            replacement = records_by_id.pop(item.component_id, None)
            if replacement is None:
                updated_items.append(item)
                continue
            saved = replacement.model_copy(update={"created_at": item.created_at})
            updated_items.append(saved)
            saved_by_id[saved.component_id] = saved
        for record in records_by_id.values():
            updated_items.append(record)
            saved_by_id[record.component_id] = record
        saved_records = [saved_by_id[record.component_id] for record in records]
        return updated_items, saved_records

    installed = _plugin_reference_components.transact(upsert)
    views = [_plugin_reference_record_view(record) for record in installed]
    _record_plugin_reference_component_event(
        "Installed plugin reference components.",
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        actor=actor,
        components=views,
    )
    return PluginReferenceComponentActivationResponse(
        plugin_id=plugin.plugin_id,
        manifest_digest=plugin.manifest_digest,
        components=views,
    )


def disable_plugin_reference_components(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> PluginReferenceComponentActivationResponse:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    now = datetime.now(UTC)
    disabled: list[PluginReferenceComponentRecord] = []

    def disable(
        items: list[PluginReferenceComponentRecord],
    ) -> tuple[list[PluginReferenceComponentRecord], list[PluginReferenceComponentRecord]]:
        updated_items: list[PluginReferenceComponentRecord] = []
        for item in items:
            if item.plugin_id == normalized_plugin_id:
                updated = item.model_copy(
                    update={
                        "status": "disabled",
                        "installed_by": actor or item.installed_by,
                        "updated_at": now,
                    }
                )
                updated_items.append(updated)
                disabled.append(updated)
            else:
                updated_items.append(item)
        return updated_items, disabled

    disabled_records = _plugin_reference_components.transact(disable)
    views = [_plugin_reference_record_view(record) for record in disabled_records]
    _record_plugin_reference_component_event(
        "Disabled plugin reference components.",
        plugin_id=normalized_plugin_id,
        manifest_digest="",
        actor=actor,
        components=views,
    )
    return PluginReferenceComponentActivationResponse(
        plugin_id=normalized_plugin_id,
        components=views,
    )


def list_plugin_reference_components(plugin_id: str) -> PluginReferenceComponentActivationResponse:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    records = [
        record
        for record in _plugin_reference_components.list()
        if record.plugin_id == normalized_plugin_id
    ]
    return PluginReferenceComponentActivationResponse(
        plugin_id=normalized_plugin_id,
        manifest_digest="",
        components=[_plugin_reference_record_view(record) for record in records],
    )


def _plugin_reference_record_view(
    record: PluginReferenceComponentRecord,
) -> PluginReferenceComponentActivationView:
    return PluginReferenceComponentActivationView(
        component_id=record.component_id,
        component_type=record.component_type,
        name=record.name,
        component_path=record.component_path,
        component_digest=record.component_digest,
        component_size_bytes=record.component_size_bytes,
        manifest_digest=record.manifest_digest,
        status=record.status,
    )


def _preview_reference_component_view(
    component: _LoadedPluginReferenceComponent,
    manifest_digest: str,
) -> PluginReferenceComponentPreviewView:
    return PluginReferenceComponentPreviewView(
        component_id=component.component_id,
        component_type=component.component_type,
        name=component.name,
        component_path=component.component_path,
        component_digest=component.component_digest,
        component_size_bytes=component.component_size_bytes,
        manifest_digest=manifest_digest,
    )


def validate_plugin_component_activation(
    plugin_id: str,
    manifest_digest: str,
    component_path: str,
    component_digest: str,
) -> None:
    try:
        plugin = get_plugin(plugin_id)
    except (KeyError, ValueError) as exc:
        raise PermissionError("Plugin command recipe source is not available.") from exc
    if plugin.trust_status != "trusted" or plugin.manifest_digest != manifest_digest:
        raise PermissionError("Plugin command recipe source is not currently trusted.")
    if plugin.trusted_manifest_digest != manifest_digest:
        raise PermissionError("Plugin command recipe source trust digest has drifted.")
    raw_component = _read_plugin_component_bytes(plugin.plugin_id, component_path)
    if sha256(raw_component).hexdigest() != component_digest:
        raise PermissionError("Plugin command recipe component digest has drifted.")


def _plugin_view_from_manifest_path(manifest_path: Path) -> PluginDiscoveryView:
    raw_manifest = _read_manifest_bytes(manifest_path)
    digest = sha256(raw_manifest).hexdigest()
    try:
        parsed = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Plugin manifest is invalid.") from exc
    try:
        manifest = PluginManifest.model_validate(parsed)
    except ValueError as exc:
        raise ValueError("Plugin manifest is invalid.") from exc
    if manifest.plugin_id != manifest_path.parent.name:
        raise ValueError("Plugin manifest id must match its directory name.")
    trust_record = _plugin_trust.get(manifest.plugin_id)
    trust_status: PluginTrustStatus = "untrusted"
    if trust_record is not None:
        trust_status = trust_record.status if trust_record.manifest_digest == digest else "stale"
    return PluginDiscoveryView(
        plugin_id=manifest.plugin_id,
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        source=manifest.source,
        components=manifest.components,
        command_recipes=manifest.command_recipes,
        hook_policies=manifest.hook_policies,
        agent_blueprints=manifest.agent_blueprints,
        skills=manifest.skills,
        tools=manifest.tools,
        docs=manifest.docs,
        manifest_path=_relative_plugin_path(manifest_path),
        manifest_digest=digest,
        manifest_size_bytes=len(raw_manifest),
        trust_status=trust_status,
        trust_reason=trust_record.reason if trust_record else "",
        trusted_manifest_digest=trust_record.manifest_digest if trust_record else "",
        decided_by=trust_record.decided_by if trust_record else "",
        trust_updated_at=trust_record.updated_at if trust_record else None,
    )


def _read_manifest_bytes(manifest_path: Path) -> bytes:
    plugins_dir = _plugins_dir()
    if plugins_dir.is_symlink() or not plugins_dir.is_dir():
        raise ValueError("Plugin directory is invalid.")
    try:
        resolved_plugins_dir = plugins_dir.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Plugin directory is invalid.") from exc
    try:
        resolved = manifest_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Plugin manifest is invalid.") from exc
    if resolved_plugins_dir != resolved.parent.parent or resolved.name != PLUGIN_MANIFEST_NAME:
        raise ValueError("Plugin manifest is outside the plugin directory.")
    if manifest_path.is_symlink() or manifest_path.parent.is_symlink():
        raise ValueError("Plugin manifest is invalid.")
    try:
        pre_open_stat = os.stat(resolved, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("Plugin manifest is invalid.") from exc
    if not S_ISREG(pre_open_stat.st_mode):
        raise ValueError("Plugin manifest is invalid.")
    if pre_open_stat.st_size > PLUGIN_MANIFEST_MAX_BYTES:
        raise ValueError("Plugin manifest is too large.")
    raw_manifest = _read_bounded_manifest(resolved, pre_open_stat)
    if len(raw_manifest) > PLUGIN_MANIFEST_MAX_BYTES:
        raise ValueError("Plugin manifest is too large.")
    try:
        post_read_resolved = manifest_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Plugin manifest is invalid.") from exc
    if post_read_resolved != resolved or not post_read_resolved.is_file():
        raise ValueError("Plugin manifest is invalid.")
    if manifest_path.is_symlink() or manifest_path.parent.is_symlink():
        raise ValueError("Plugin manifest is invalid.")
    return raw_manifest


def _trusted_plugin_for_activation(plugin_id: str) -> PluginDiscoveryView:
    plugin = get_plugin(plugin_id)
    if plugin.trust_status != "trusted":
        raise PermissionError("Plugin must be trusted at the current manifest digest.")
    if plugin.trusted_manifest_digest != plugin.manifest_digest:
        raise PermissionError("Plugin trust digest has drifted.")
    return plugin


def _load_plugin_command_recipe_components(
    plugin: PluginDiscoveryView,
) -> list[tuple[CommandRecipeRequest, str, str]]:
    loaded: list[tuple[CommandRecipeRequest, str, str]] = []
    seen_recipe_ids: set[str] = set()
    for component in plugin.command_recipes:
        raw_component = _read_plugin_component_bytes(plugin.plugin_id, component.path)
        try:
            payload = json.loads(raw_component.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Plugin command recipe component is invalid.") from exc
        try:
            recipe = CommandRecipeRequest.model_validate(payload)
        except ValueError as exc:
            raise ValueError("Plugin command recipe component is invalid.") from exc
        if recipe.id is None:
            raise ValueError("Plugin command recipe components require stable recipe ids.")
        if recipe.id in seen_recipe_ids:
            raise ValueError(f"Duplicate plugin command recipe id: {recipe.id}")
        seen_recipe_ids.add(recipe.id)
        loaded.append((recipe, component.path, sha256(raw_component).hexdigest()))
    return loaded


def _load_plugin_hook_policy_components(
    plugin: PluginDiscoveryView,
) -> list[tuple[str, HookPolicyRuleRequest, str, str]]:
    loaded: list[tuple[str, HookPolicyRuleRequest, str, str]] = []
    seen_rule_ids: set[str] = set()
    rule_count = 0
    for component in plugin.hook_policies:
        raw_component = _read_plugin_component_bytes(plugin.plugin_id, component.path)
        component_digest = sha256(raw_component).hexdigest()
        try:
            payload = json.loads(raw_component.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Plugin hook policy component is invalid.") from exc
        payloads = payload if isinstance(payload, list) else [payload]
        for index, rule_payload in enumerate(payloads):
            rule_count += 1
            if rule_count > PLUGIN_HOOK_POLICY_MAX_RULES:
                raise ValueError("Plugin hook policy components declare too many rules.")
            try:
                rule = HookPolicyRuleRequest.model_validate(rule_payload)
                rule = validate_hook_policy_rule_request(rule)
            except ValueError as exc:
                raise ValueError("Plugin hook policy component is invalid.") from exc
            rule_id = _plugin_hook_policy_rule_id(plugin.plugin_id, component.path, index)
            if rule_id in seen_rule_ids:
                raise ValueError(f"Duplicate plugin hook policy rule id: {rule_id}")
            seen_rule_ids.add(rule_id)
            loaded.append((rule_id, rule, component.path, component_digest))
    return loaded


def _load_plugin_reference_components(
    plugin: PluginDiscoveryView,
) -> list[_LoadedPluginReferenceComponent]:
    loaded: list[_LoadedPluginReferenceComponent] = []
    seen_components: set[tuple[str, str]] = set()
    reference_groups: tuple[
        tuple[PluginReferenceComponentType, list[PluginReferenceComponent]],
        ...,
    ] = (
        ("agent_blueprints", plugin.agent_blueprints),
        ("skills", plugin.skills),
        ("tools", plugin.tools),
        ("docs", plugin.docs),
    )
    for component_type, components in reference_groups:
        for component in components:
            component_key = (component_type, component.path)
            if component_key in seen_components:
                raise ValueError("Duplicate plugin component reference.")
            seen_components.add(component_key)
            raw_component = _read_plugin_component_bytes(plugin.plugin_id, component.path)
            loaded.append(
                _LoadedPluginReferenceComponent(
                    component_id=_plugin_reference_component_id(
                        plugin.plugin_id,
                        component_type,
                        component.path,
                    ),
                    component_type=component_type,
                    name=component.name or component.path,
                    component_path=component.path,
                    component_digest=sha256(raw_component).hexdigest(),
                    component_size_bytes=len(raw_component),
                )
            )
    return loaded


def _plugin_hook_policy_rule_id(plugin_id: str, component_path: str, index: int) -> str:
    seed = f"{plugin_id}\0{component_path}\0{index}".encode()
    return f"{plugin_id}.hook-{sha256(seed).hexdigest()[:16]}"


def _plugin_reference_component_id(
    plugin_id: str,
    component_type: PluginReferenceComponentType,
    component_path: str,
) -> str:
    seed = f"{plugin_id}\0{component_type}\0{component_path}".encode()
    return f"{plugin_id}.component-{sha256(seed).hexdigest()[:16]}"


def _read_plugin_component_bytes(plugin_id: str, component_path: str) -> bytes:
    normalized_plugin_id = _normalize_plugin_id(plugin_id)
    normalized_component_path = _normalize_component_path(component_path)
    plugin_dir = _plugins_dir() / normalized_plugin_id
    if plugin_dir.is_symlink() or not plugin_dir.is_dir():
        raise ValueError("Plugin directory is invalid.")
    try:
        resolved_plugin_dir = plugin_dir.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Plugin directory is invalid.") from exc
    candidate = plugin_dir.joinpath(*normalized_component_path.split("/"))
    _reject_symlinked_component_path(plugin_dir, normalized_component_path)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Plugin command recipe component is invalid.") from exc
    try:
        resolved.relative_to(resolved_plugin_dir)
    except ValueError as exc:
        raise ValueError(
            "Plugin command recipe component is outside the plugin directory."
        ) from exc
    if candidate.is_symlink():
        raise ValueError("Plugin command recipe component is invalid.")
    try:
        pre_open_stat = os.stat(resolved, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("Plugin command recipe component is invalid.") from exc
    if not S_ISREG(pre_open_stat.st_mode):
        raise ValueError("Plugin command recipe component is invalid.")
    if pre_open_stat.st_size > PLUGIN_COMPONENT_MAX_BYTES:
        raise ValueError("Plugin command recipe component is too large.")
    raw_component = _read_bounded_component(resolved, pre_open_stat)
    if len(raw_component) > PLUGIN_COMPONENT_MAX_BYTES:
        raise ValueError("Plugin command recipe component is too large.")
    try:
        post_read_resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Plugin command recipe component is invalid.") from exc
    if post_read_resolved != resolved or not post_read_resolved.is_file():
        raise ValueError("Plugin command recipe component is invalid.")
    _reject_symlinked_component_path(plugin_dir, normalized_component_path)
    return raw_component


def _read_bounded_component(component_path: Path, expected_stat: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(component_path, flags)
    except OSError as exc:
        raise ValueError("Plugin command recipe component is invalid.") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            opened_stat = os.fstat(stream.fileno())
            if not S_ISREG(opened_stat.st_mode):
                raise ValueError("Plugin command recipe component is invalid.")
            if opened_stat.st_size > PLUGIN_COMPONENT_MAX_BYTES:
                raise ValueError("Plugin command recipe component is too large.")
            if not _same_file_snapshot(opened_stat, expected_stat):
                raise ValueError("Plugin command recipe component is invalid.")
            raw_component = stream.read(PLUGIN_COMPONENT_MAX_BYTES + 1)
            try:
                post_read_stat = os.stat(component_path, follow_symlinks=False)
            except OSError as exc:
                raise ValueError("Plugin command recipe component is invalid.") from exc
            if not _same_file_snapshot(opened_stat, post_read_stat):
                raise ValueError("Plugin command recipe component is invalid.")
            return raw_component
    finally:
        if fd >= 0:
            os.close(fd)


def _reject_symlinked_component_path(plugin_dir: Path, component_path: str) -> None:
    current = plugin_dir
    for part in component_path.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError("Plugin command recipe component is invalid.")


def _normalize_component_path(value: str) -> str:
    stripped = value.strip().replace("\\", "/")
    if not stripped or redact_sensitive_values(stripped) != stripped:
        raise ValueError("Plugin component paths must use safe relative paths.")
    posix_path = PurePosixPath(stripped)
    windows_path = PureWindowsPath(stripped)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("Plugin component paths must be relative.")
    parts = [part for part in posix_path.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Plugin component paths must stay inside the plugin directory.")
    return "/".join(parts)


def _read_bounded_manifest(manifest_path: Path, expected_stat: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(manifest_path, flags)
    except OSError as exc:
        raise ValueError("Plugin manifest is invalid.") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            opened_stat = os.fstat(stream.fileno())
            if not S_ISREG(opened_stat.st_mode):
                raise ValueError("Plugin manifest is invalid.")
            if opened_stat.st_size > PLUGIN_MANIFEST_MAX_BYTES:
                raise ValueError("Plugin manifest is too large.")
            if not _same_file_snapshot(opened_stat, expected_stat):
                raise ValueError("Plugin manifest is invalid.")
            raw_manifest = stream.read(PLUGIN_MANIFEST_MAX_BYTES + 1)
            try:
                post_read_stat = os.stat(manifest_path, follow_symlinks=False)
            except OSError as exc:
                raise ValueError("Plugin manifest is invalid.") from exc
            if not _same_file_snapshot(opened_stat, post_read_stat):
                raise ValueError("Plugin manifest is invalid.")
            return raw_manifest
    finally:
        if fd >= 0:
            os.close(fd)


def _same_file_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and getattr(left, "st_mtime_ns", None) == getattr(right, "st_mtime_ns", None)
    )


def _plugins_dir() -> Path:
    return get_settings().root_dir.resolve() / "plugins"


def _relative_plugin_path(path: Path) -> str:
    try:
        relative_path = path.resolve(strict=False).relative_to(get_settings().root_dir.resolve())
    except ValueError:
        return "plugins"
    return "/".join(redact_sensitive_values(part)[:120] for part in relative_path.parts)


def _normalize_plugin_id(plugin_id: str) -> str:
    stripped = plugin_id.strip()
    if not stripped:
        raise ValueError("Plugin id must not be blank.")
    PluginManifest(plugin_id=stripped, name="placeholder", version="0")
    return stripped


def _record_plugin_trust_event(
    record: PluginTrustRecord,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.tool,
        "Updated plugin trust.",
        actor=actor or "system",
        subject_id=record.plugin_id,
        metadata={
            "plugin_id": record.plugin_id,
            "manifest_digest": record.manifest_digest,
            "status": record.status,
            "reason": redact_sensitive_values(record.reason),
            "decided_by": redact_sensitive_values(record.decided_by),
        },
    )


def _record_plugin_activation_event(
    message: str,
    *,
    plugin_id: str,
    manifest_digest: str,
    actor: str | None,
    command_recipes: list[PluginCommandRecipeActivationView],
) -> None:
    event_log.record(
        LogEventType.tool,
        message,
        actor=actor or "system",
        subject_id=plugin_id,
        metadata={
            "plugin_id": plugin_id,
            "manifest_digest": manifest_digest,
            "command_recipe_ids": [recipe.recipe_id for recipe in command_recipes],
            "component_paths": [
                redact_sensitive_values(recipe.component_path) for recipe in command_recipes
            ],
            "component_digests": [recipe.component_digest for recipe in command_recipes],
            "statuses": [recipe.status for recipe in command_recipes],
        },
    )


def _record_plugin_hook_policy_activation_event(
    message: str,
    *,
    plugin_id: str,
    manifest_digest: str,
    actor: str | None,
    hook_policies: list[PluginHookPolicyActivationView],
) -> None:
    event_log.record(
        LogEventType.tool,
        message,
        actor=actor or "system",
        subject_id=plugin_id,
        metadata={
            "plugin_id": plugin_id,
            "manifest_digest": manifest_digest,
            "hook_policy_rule_ids": [rule.rule_id for rule in hook_policies],
            "component_paths": [
                redact_sensitive_values(rule.component_path) for rule in hook_policies
            ],
            "component_digests": [rule.component_digest for rule in hook_policies],
            "statuses": [rule.status for rule in hook_policies],
        },
    )


def _record_plugin_reference_component_event(
    message: str,
    *,
    plugin_id: str,
    manifest_digest: str,
    actor: str | None,
    components: list[PluginReferenceComponentActivationView],
) -> None:
    event_log.record(
        LogEventType.tool,
        message,
        actor=actor or "system",
        subject_id=plugin_id,
        metadata={
            "plugin_id": plugin_id,
            "manifest_digest": manifest_digest,
            "component_ids": [component.component_id for component in components],
            "component_types": [component.component_type for component in components],
            "component_paths": [
                redact_sensitive_values(component.component_path) for component in components
            ],
            "component_digests": [component.component_digest for component in components],
            "statuses": [component.status for component in components],
        },
    )
