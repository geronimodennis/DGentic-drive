from uuid import uuid4

from dgentic.schemas import LogEvent, LogEventType


class EventLog:
    def __init__(self) -> None:
        self._events: list[LogEvent] = []

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
        self._events.append(event)
        return event

    def list(self, event_type: LogEventType | None = None) -> list[LogEvent]:
        if event_type is None:
            return list(self._events)
        return [event for event in self._events if event.event_type == event_type]


event_log = EventLog()
