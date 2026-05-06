from dgentic.events import event_log
from dgentic.schemas import LogEventType, ToolManifest
from dgentic.storage import JsonCollection

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
