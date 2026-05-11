from datetime import UTC, datetime
from uuid import uuid4

from dgentic.events import event_log
from dgentic.schemas import (
    AgentBrief,
    AgentOutput,
    AgentReconciliation,
    AgentStatus,
    AgentStatusUpdate,
    LogEventType,
)
from dgentic.storage import JsonCollection

_agents = JsonCollection("agents", AgentBrief)


def spawn_agent(brief: AgentBrief, *, actor: str | None = None) -> AgentBrief:
    agent = brief.model_copy(
        update={"id": brief.id or f"agent-{uuid4()}", "status": AgentStatus.running}
    )
    _agents.upsert(agent)
    event_log.record(
        LogEventType.agent,
        "Spawned sub-agent brief.",
        actor=actor or "system",
        subject_id=agent.id,
        metadata=agent.model_dump(),
    )
    return agent


def list_agents() -> list[AgentBrief]:
    return _agents.list()


def get_agent(agent_id: str) -> AgentBrief | None:
    return _agents.get(agent_id)


def list_child_agents(parent_agent_id: str) -> list[AgentBrief]:
    return [agent for agent in _agents.list() if agent.parent_agent_id == parent_agent_id]


def update_agent_status(
    agent_id: str,
    update: AgentStatusUpdate,
    *,
    actor: str | None = None,
) -> AgentBrief | None:
    agent = get_agent(agent_id)
    if agent is None:
        return None
    terminal_statuses = {AgentStatus.completed, AgentStatus.failed, AgentStatus.cancelled}
    completed_at = datetime.now(UTC) if update.status in terminal_statuses else None
    updated = agent.model_copy(update={"status": update.status, "completed_at": completed_at})
    _agents.upsert(updated)
    event_log.record(
        LogEventType.agent,
        "Updated agent lifecycle status.",
        actor=actor or "system",
        subject_id=agent_id,
        metadata={"status": update.status, "note": update.note},
    )
    return updated


def reconcile_outputs(
    outputs: list[AgentOutput],
    *,
    actor: str | None = None,
) -> AgentReconciliation:
    conflicts = [issue for output in outputs for issue in output.unresolved_issues]
    confidence = sum(output.confidence for output in outputs) / len(outputs) if outputs else 0.0
    reconciliation = AgentReconciliation(
        accepted_outputs=outputs,
        conflicts=conflicts,
        confidence=confidence,
    )
    event_log.record(
        LogEventType.agent,
        "Reconciled agent outputs.",
        actor=actor or "system",
        metadata=reconciliation.model_dump(),
    )
    return reconciliation
