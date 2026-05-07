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


class CommandPolicyMatchType(StrEnum):
    executable = "executable"
    exact = "exact"
    contains = "contains"
    argument_contains = "argument_contains"


class MemoryKind(StrEnum):
    note = "note"
    decision = "decision"
    artifact = "artifact"
    summary = "summary"


class ToolTriggerSource(StrEnum):
    main_agent = "main_agent"
    sub_agent = "sub_agent"
    skill = "skill"
    module = "module"


class ToolStatus(StrEnum):
    active = "active"
    deprecated = "deprecated"
    disabled = "disabled"


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
    capabilities: list[str] = Field(default_factory=list)
    estimated_latency_ms: int | None = None
    estimated_cost_usd: float | None = None
    permission_mode: PermissionMode = PermissionMode.approval_required
    enabled: bool = True


class ProviderHealth(BaseModel):
    provider_id: str
    available: bool
    message: str
    model_names: list[str] = Field(default_factory=list)
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
    candidate_scores: dict[str, float] = Field(default_factory=dict)


class AgentBrief(BaseModel):
    id: str = ""
    role: str
    task: str
    parent_agent_id: str | None = None
    task_id: str | None = None
    context: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    expected_output: str
    status: AgentStatus = AgentStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class AgentStatusUpdate(BaseModel):
    status: AgentStatus
    note: str | None = None


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
    version: str = "0.2.4"
    description: str
    entrypoint: str
    permission_mode: PermissionMode
    tags: list[str] = Field(default_factory=list)
    interface: dict[str, Any] = Field(default_factory=dict)
    status: ToolStatus = ToolStatus.active
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_used_at: datetime | None = None
    deprecated_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolGenerationRequest(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    description: str = Field(min_length=1)
    trigger_source: ToolTriggerSource
    permission_mode: PermissionMode = PermissionMode.approval_required
    tags: list[str] = Field(default_factory=list)
    version: str = "0.2.4"
    source_code: str | None = None
    interface: dict[str, Any] = Field(default_factory=dict)
    overwrite: bool = False


class ToolGenerationResult(BaseModel):
    manifest: ToolManifest
    tool_dir: Path
    files_created: list[Path]
    duplicate_detected: bool = False


class ToolGovernanceUpdate(BaseModel):
    status: ToolStatus
    reason: str | None = None


class ToolExecutionRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class FileAccessRequest(BaseModel):
    path: Path
    action: Literal["read", "write", "delete"]


class FileAccessDecision(BaseModel):
    path: Path
    resolved_path: Path
    allowed: bool
    permission_mode: PermissionMode
    reason: str


class FileReadRequest(BaseModel):
    path: Path


class FileReadResponse(BaseModel):
    path: Path
    content: str
    bytes_read: int


class FileWriteRequest(BaseModel):
    path: Path
    content: str
    create_parent_dirs: bool = True


class FileWriteResponse(BaseModel):
    path: Path
    bytes_written: int


class CommandPolicyRequest(BaseModel):
    command: str
    agent_role: str | None = None
    agent_id: str | None = None
    task_id: str | None = None

    @field_validator("command")
    @classmethod
    def command_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Command must not be empty.")
        return value


class CommandPolicyRuleRequest(BaseModel):
    name: str = Field(min_length=1)
    match_type: CommandPolicyMatchType = CommandPolicyMatchType.executable
    pattern: str = Field(min_length=1)
    permission_mode: PermissionMode
    reason: str = Field(min_length=1)
    agent_roles: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10_000)

    @field_validator("name", "pattern", "reason")
    @classmethod
    def policy_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Policy rule text fields must not be blank.")
        return value


class CommandPolicyRule(CommandPolicyRuleRequest):
    id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommandPolicyRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    match_type: CommandPolicyMatchType | None = None
    pattern: str | None = Field(default=None, min_length=1)
    permission_mode: PermissionMode | None = None
    reason: str | None = Field(default=None, min_length=1)
    agent_roles: list[str] | None = None
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("name", "pattern", "reason")
    @classmethod
    def optional_policy_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Policy rule text fields must not be blank.")
        return value


class CommandPolicyDecision(BaseModel):
    command: str
    risk: CommandRisk
    permission_mode: PermissionMode
    reason: str
    agent_role: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    matched_rule_id: str | None = None
    matched_rule_name: str | None = None


class CommandExecutionRequest(BaseModel):
    command: str
    cwd: Path | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    approved: bool = False
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def command_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Command must not be empty.")
        return value


class CommandExecutionResult(BaseModel):
    command: str
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    permission_mode: PermissionMode
    duration_ms: int
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    environment_keys: list[str] = Field(default_factory=list)


class CommandApprovalDecisionRequest(BaseModel):
    decided_by: str | None = None
    reason: str | None = None


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
