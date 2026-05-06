from uuid import uuid4

from dgentic.events import event_log
from dgentic.schemas import AgentBrief, AgentOutput, AgentReconciliation, AgentStatus, LogEventType

_agents: dict[str, AgentBrief] = {}


def spawn_agent(brief: AgentBrief) -> AgentBrief:
    agent = brief.model_copy(
        update={"id": brief.id or f"agent-{uuid4()}", "status": AgentStatus.running}
    )
    _agents[agent.id] = agent
    event_log.record(
        LogEventType.agent,
        "Spawned sub-agent brief.",
        subject_id=agent.id,
        metadata=agent.model_dump(),
    )
    return agent


def list_agents() -> list[AgentBrief]:
    return list(_agents.values())


def reconcile_outputs(outputs: list[AgentOutput]) -> AgentReconciliation:
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
        metadata=reconciliation.model_dump(),
    )
    return reconciliation
