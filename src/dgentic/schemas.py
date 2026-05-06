from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class AgentBrief(BaseModel):
    id: str
    role: str
    task: str
    context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    expected_output: str
    status: AgentStatus = AgentStatus.pending


class ToolManifest(BaseModel):
    name: str
    version: str = "0.1.0"
    description: str
    entrypoint: str
    permission_mode: PermissionMode
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LogEvent(BaseModel):
    id: str
    event_type: LogEventType
    message: str
    actor: str = "system"
    subject_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
