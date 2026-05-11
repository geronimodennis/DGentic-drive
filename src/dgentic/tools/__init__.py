"""Tool generation services and SQLAlchemy registry service."""

from __future__ import annotations

import json
from hashlib import sha256

from sqlalchemy.exc import SQLAlchemyError

from dgentic.database import get_db_session
from dgentic.events import event_log
from dgentic.memory import add_memory
from dgentic.memory.schemas import DuplicateCheckRequest, ToolRegistryCreateRequest
from dgentic.schemas import (
    LogEventType,
    MemoryKind,
    MemoryRecord,
    PermissionMode,
    ToolGenerationRequest,
    ToolGenerationResult,
    ToolGovernanceUpdate,
    ToolManifest,
    ToolStatus,
)
from dgentic.settings import get_settings
from dgentic.storage import JsonCollection
from dgentic.tools.registry_service import ToolRegistryService

_tools = JsonCollection("tools", ToolManifest, key_field="name")


def register_tool(manifest: ToolManifest) -> ToolManifest:
    _tools.upsert(manifest)
    event_log.record(
        LogEventType.tool,
        "Registered local tool manifest.",
        subject_id=manifest.name,
        metadata=manifest.model_dump(mode="json"),
    )
    return manifest


def list_tools() -> list[ToolManifest]:
    return _tools.list()


def get_tool(name: str) -> ToolManifest | None:
    return _tools.get(name)


def save_tool_manifest(manifest: ToolManifest) -> ToolManifest:
    return _tools.upsert(manifest)


def generate_tool(request: ToolGenerationRequest) -> ToolGenerationResult:
    if request.permission_mode == PermissionMode.blocked:
        raise PermissionError("Generated tools cannot be registered with blocked permission mode.")

    interface = request.interface or {"input": "dict", "output": "dict"}
    interface_signature = _interface_signature(interface)
    _ensure_sql_registry_allows_generation(request, interface_signature)

    existing = _find_duplicate(request)
    if existing and not request.overwrite:
        raise FileExistsError(f"Tool already exists or duplicates existing tool: {existing.name}")

    root_dir = get_settings().root_dir.resolve()
    localmcp_dir = (root_dir / "localmcp").resolve()
    tool_dir = (localmcp_dir / request.name).resolve()
    if localmcp_dir != tool_dir and localmcp_dir not in tool_dir.parents:
        raise PermissionError("Generated tools must stay inside rootDir/localmcp.")
    if tool_dir.exists() and not request.overwrite:
        raise FileExistsError(f"Tool directory already exists: {tool_dir}")

    tool_dir.mkdir(parents=True, exist_ok=True)
    source_path = tool_dir / "tool.py"
    wrapper_path = tool_dir / "wrapper.py"
    manifest_path = tool_dir / "manifest.json"
    readme_path = tool_dir / "README.md"

    source_code = request.source_code or _default_source(request)
    source_path.write_text(source_code, encoding="utf-8")
    wrapper_path.write_text(_wrapper_source(), encoding="utf-8")

    manifest = ToolManifest(
        name=request.name,
        version=request.version,
        description=request.description,
        entrypoint=str(source_path.relative_to(root_dir)),
        permission_mode=request.permission_mode,
        tags=sorted(set(request.tags + [request.trigger_source.value])),
        interface=interface,
        dependency_paths=request.dependency_paths,
    )
    manifest_json = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    manifest_path.write_text(manifest_json, encoding="utf-8")
    readme_path.write_text(_readme(request, manifest), encoding="utf-8")
    register_tool(manifest)
    _register_sql_tool_manifest(request, manifest, interface_signature)
    add_memory(
        MemoryRecord(
            kind=MemoryKind.artifact,
            title=f"Generated tool: {manifest.name}",
            content=manifest.description,
            tags=sorted(set(manifest.tags + ["tool", "localmcp"])),
            relevance=0.8,
        )
    )

    result = ToolGenerationResult(
        manifest=manifest,
        tool_dir=tool_dir,
        files_created=[source_path, wrapper_path, manifest_path, readme_path],
        duplicate_detected=existing is not None,
    )
    event_log.record(
        LogEventType.tool,
        "Generated local tool.",
        subject_id=manifest.name,
        metadata={
            "tool_dir": str(tool_dir),
            "files_created": [str(path) for path in result.files_created],
            "trigger_source": request.trigger_source,
            "permission_mode": request.permission_mode,
        },
    )
    return result


def update_tool_governance(name: str, update: ToolGovernanceUpdate) -> ToolManifest | None:
    tool = next((item for item in _tools.list() if item.name == name), None)
    if tool is None:
        return None
    updated = tool.model_copy(
        update={
            "status": update.status,
            "deprecated_reason": update.reason if update.status != ToolStatus.active else None,
        }
    )
    register_tool(updated)
    event_log.record(
        LogEventType.tool,
        "Updated local tool governance.",
        subject_id=name,
        metadata={"status": update.status, "reason": update.reason},
    )
    return updated


def _find_duplicate(request: ToolGenerationRequest) -> ToolManifest | None:
    requested_tags = set(request.tags)
    for tool in _tools.list():
        if tool.name == request.name:
            return tool
        if (
            requested_tags
            and requested_tags.intersection(tool.tags)
            and tool.description == request.description
        ):
            return tool
        if request.interface and tool.interface == request.interface:
            return tool
    return None


def _interface_signature(interface: dict) -> str:
    payload = json.dumps(interface, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


def _ensure_sql_registry_allows_generation(
    request: ToolGenerationRequest,
    interface_signature: str,
) -> None:
    session = get_db_session()
    try:
        service = ToolRegistryService(session)
        existing = service.get_tool_by_name(request.name)
        if existing is not None:
            raise FileExistsError(f"Tool already exists in SQL registry: {existing.tool_name}")

        duplicate = service.check_duplicate(
            DuplicateCheckRequest(
                tool_name=request.name,
                interface_signature=interface_signature,
                tags=request.tags,
            )
        )
        similar_names = {
            str(item.get("tool_name"))
            for item in duplicate.get("similar_tools", [])
            if item.get("tool_name") is not None
        }
        different_tool_duplicate = similar_names - {request.name}
        if duplicate.get("is_duplicate") and (not request.overwrite or different_tool_duplicate):
            raise FileExistsError(duplicate["recommendation"])
    finally:
        session.close()


def _register_sql_tool_manifest(
    request: ToolGenerationRequest,
    manifest: ToolManifest,
    interface_signature: str,
) -> None:
    session = get_db_session()
    try:
        service = ToolRegistryService(session)
        if service.get_tool_by_name(manifest.name) is not None:
            return
        service.register_tool(
            ToolRegistryCreateRequest(
                tool_name=manifest.name,
                version=manifest.version,
                source_path=manifest.entrypoint,
                interface_signature=interface_signature,
                permission_level=manifest.permission_mode.value,
                tags=manifest.tags,
                description=manifest.description,
                created_by_agent=request.trigger_source.value,
            )
        )
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Failed to register generated tool in SQL registry: {exc}") from exc
    finally:
        session.close()


def _default_source(request: ToolGenerationRequest) -> str:
    return (
        '"""Generated DGentic local tool."""\n\n'
        "from typing import Any\n\n\n"
        "def run(payload: dict[str, Any]) -> dict[str, Any]:\n"
        f'    """{request.description}"""\n'
        '    return {"ok": True, "payload": payload}\n'
    )


def _wrapper_source() -> str:
    return (
        '"""Interface wrapper for a generated DGentic local tool."""\n\n'
        "from tool import run\n\n\n"
        "def invoke(payload):\n"
        "    return run(payload)\n"
    )


def _readme(request: ToolGenerationRequest, manifest: ToolManifest) -> str:
    permission_note = (
        "Runs without approval."
        if manifest.permission_mode == PermissionMode.autopilot_safe
        else "Requires approval."
    )
    return (
        f"# {manifest.name}\n\n"
        f"{manifest.description}\n\n"
        f"- Version: `{manifest.version}`\n"
        f"- Trigger source: `{request.trigger_source}`\n"
        f"- Permission mode: `{manifest.permission_mode}`\n"
        f"- Dependency paths: `{manifest.dependency_paths or ['vendor']}`\n"
        f"- Governance status: `{manifest.status}`\n"
        f"- Permission note: {permission_note}\n"
    )


__all__ = [
    "ToolRegistryService",
    "generate_tool",
    "get_tool",
    "list_tools",
    "register_tool",
    "save_tool_manifest",
    "update_tool_governance",
]
