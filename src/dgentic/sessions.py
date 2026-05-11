from uuid import uuid4

from dgentic.events import event_log
from dgentic.schemas import LogEventType, SessionSummary
from dgentic.storage import JsonCollection

_summaries = JsonCollection("sessions", SessionSummary)


def create_session_summary(summary: SessionSummary, *, actor: str | None = None) -> SessionSummary:
    saved = summary.model_copy(update={"id": summary.id or f"session-{uuid4()}"})
    _summaries.upsert(saved)
    event_log.record(
        LogEventType.session,
        "Created session summary.",
        actor=actor or "system",
        subject_id=saved.id,
        metadata={"next_steps": saved.next_steps, "created_tools": saved.created_tools},
    )
    return saved


def list_session_summaries() -> list[SessionSummary]:
    return _summaries.list()
