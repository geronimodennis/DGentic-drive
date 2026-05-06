from uuid import uuid4

from dgentic.events import event_log
from dgentic.schemas import LogEventType, SessionSummary

_summaries: dict[str, SessionSummary] = {}


def create_session_summary(summary: SessionSummary) -> SessionSummary:
    saved = summary.model_copy(update={"id": summary.id or f"session-{uuid4()}"})
    _summaries[saved.id] = saved
    event_log.record(
        LogEventType.session,
        "Created session summary.",
        subject_id=saved.id,
        metadata={"next_steps": saved.next_steps, "created_tools": saved.created_tools},
    )
    return saved


def list_session_summaries() -> list[SessionSummary]:
    return list(_summaries.values())
