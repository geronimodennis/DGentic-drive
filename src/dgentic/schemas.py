from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    environment: str


class Priority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"


class PlanStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    running = "running"
    completed = "completed"
    failed = "failed"


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"


class PermissionMode(StrEnum):
    autopilot_safe = "autopilot_safe"
    approval_required = "approval_required"
    blocked = "blocked"


class ProviderKind(StrEnum):
    local = "local"
    external = "external"


class AgentStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class LogEventType(StrEnum):
    task = "task"
    agent = "agent"
    provider = "provider"
    tool = "tool"
    cli = "cli"
    filesystem = "filesystem"
    approval = "approval"
    memory = "memory"
    session = "session"


class CommandRisk(StrEnum):
    safe = "safe"
    approval_required = "approval_required"
    blocked = "blocked"


class MemoryKind(StrEnum):
    note = "note"
    decision = "decision"
    artifact = "artifact"
    summary = "summary"


class TaskRequest(BaseModel):
    objective: str = Field(min_length=1, description="The user goal DGentic should plan.")
    context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Priority = Priority.normal
    requested_by: str | None = None


class PlanStep(BaseModel):
    id: str
    title: str
    description: str
    status: StepStatus = StepStatus.pending
    agent_role: str = "orchestrator"
    dependencies: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    validation: str


class TaskPlan(BaseModel):
    id: str
    objective: str
    status: PlanStatus = PlanStatus.draft
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    steps: list[PlanStep]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskRun(BaseModel):
    id: str
    plan_id: str
    status: PlanStatus = PlanStatus.running
    results: list["StepResult"] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class StepResult(BaseModel):
    step_id: str
    status: StepStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retry_count: int = 0
    completed_at: datetime | None = None


class ProviderConfig(BaseModel):
    id: str
    name: str
    kind: ProviderKind
    base_url: str | None = None
    model_names: list[str] = Field(default_factory=list)
    permission_mode: PermissionMode = PermissionMode.approval_required
    enabled: bool = True


class ProviderHealth(BaseModel):
    provider_id: str
    available: bool
    message: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoutingRequest(BaseModel):
    role: str = "planner"
    privacy_required: bool = False
    max_latency_ms: int | None = None
    max_cost_usd: float | None = None
    required_capabilities: list[str] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    provider_id: str
    model_name: str | None = None
    reason: str
    score: float
    policy: RoutingRequest


class AgentBrief(BaseModel):
    id: str = ""
    role: str
    task: str
    context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    expected_output: str
    status: AgentStatus = AgentStatus.pending


class AgentOutput(BaseModel):
    agent_id: str
    output: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved_issues: list[str] = Field(default_factory=list)


class AgentReconciliation(BaseModel):
    accepted_outputs: list[AgentOutput] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ToolManifest(BaseModel):
    name: str
    version: str = "0.1.0"
    description: str
    entrypoint: str
    permission_mode: PermissionMode
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FileAccessRequest(BaseModel):
    path: Path
    action: Literal["read", "write", "delete"]


class FileAccessDecision(BaseModel):
    path: Path
    resolved_path: Path
    allowed: bool
    permission_mode: PermissionMode
    reason: str


class CommandPolicyRequest(BaseModel):
    command: str

    @field_validator("command")
    @classmethod
    def command_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Command must not be empty.")
        return value


class CommandPolicyDecision(BaseModel):
    command: str
    risk: CommandRisk
    permission_mode: PermissionMode
    reason: str


class MemoryRecord(BaseModel):
    id: str = ""
    kind: MemoryKind = MemoryKind.note
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    usage_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryQuery(BaseModel):
    text: str = ""
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)


class MemorySearchResult(BaseModel):
    record: MemoryRecord
    score: float


class SessionSummary(BaseModel):
    id: str = ""
    actions: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    learned_knowledge: list[str] = Field(default_factory=list)
    created_tools: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LogEvent(BaseModel):
    id: str
    event_type: LogEventType
    message: str
    actor: str = "system"
    subject_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
