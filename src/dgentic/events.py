from uuid import uuid4

from dgentic.redaction import redact_metadata, redact_sensitive_values
from dgentic.schemas import LogEvent, LogEventType
from dgentic.storage import JsonCollection


class EventLog:
    def __init__(self) -> None:
        self._events = JsonCollection("events", LogEvent)

    def record(
        self,
        event_type: LogEventType,
        message: str,
        *,
        actor: str = "system",
        subject_id: str | None = None,
        metadata: dict | None = None,
    ) -> LogEvent:
        event = LogEvent(
            id=f"event-{uuid4()}",
            event_type=event_type,
            message=redact_sensitive_values(message),
            actor=redact_sensitive_values(actor),
            subject_id=redact_sensitive_values(subject_id) if subject_id else None,
            metadata=redact_metadata(metadata or {}),
        )
        self._events.upsert(event)
        return event

    def list(self, event_type: LogEventType | None = None) -> list[LogEvent]:
        events = self._events.list()
        for event in events:
            event.message = redact_sensitive_values(event.message)
            event.actor = redact_sensitive_values(event.actor)
            if event.subject_id is not None:
                event.subject_id = redact_sensitive_values(event.subject_id)
            event.metadata = redact_metadata(event.metadata)
        if event_type is None:
            return events
        return [event for event in events if event.event_type == event_type]


event_log = EventLog()
