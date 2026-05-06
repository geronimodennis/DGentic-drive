from dgentic.events import event_log
from dgentic.schemas import LogEventType, ToolManifest

_tools: dict[str, ToolManifest] = {}


def register_tool(manifest: ToolManifest) -> ToolManifest:
    key = manifest.name.lower()
    _tools[key] = manifest
    event_log.record(
        LogEventType.tool,
        "Registered local tool manifest.",
        subject_id=manifest.name,
        metadata=manifest.model_dump(mode="json"),
    )
    return manifest


def list_tools() -> list[ToolManifest]:
    return list(_tools.values())
