import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from stat import S_ISREG
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import LogEventType
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection

PLUGIN_MANIFEST_NAME = "dgentic-plugin.json"
PLUGIN_MANIFEST_MAX_BYTES = 64 * 1024
PLUGIN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$"
PluginTrustDecision = Literal["trusted", "blocked"]
PluginTrustStatus = Literal["trusted", "blocked", "untrusted", "stale"]


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


_plugin_trust = JsonCollection("plugin-trust", PluginTrustRecord, key_field="plugin_id")


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
