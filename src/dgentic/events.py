from uuid import uuid4

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
            message=message,
            actor=actor,
            subject_id=subject_id,
            metadata=metadata or {},
        )
        self._events.upsert(event)
        return event

    def list(self, event_type: LogEventType | None = None) -> list[LogEvent]:
        events = self._events.list()
        if event_type is None:
            return events
        return [event for event in events if event.event_type == event_type]


event_log = EventLog()
