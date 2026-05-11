import math
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class OrchestrationExecutionStatus(StrEnum):
    starting = "starting"
    running = "running"
    cancelling = "cancelling"
    cancelled = "cancelled"
    completed = "completed"
    failed = "failed"
    stale = "stale"


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


def _validate_tool_dependency_paths(values: list[str]) -> list[str]:
    validated: list[str] = []
    for value in values:
        dependency_path = value.strip()
        requested = Path(dependency_path)
        if (
            not dependency_path
            or requested.is_absolute()
            or requested.drive
            or not requested.parts
            or any(part in {"", ".", ".."} for part in requested.parts)
        ):
            raise ValueError(
                "dependency_paths must be relative path segments under the tool directory."
            )
        validated.append(dependency_path)
    return validated


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
    supports_streaming: bool = False


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

    @field_validator("max_cost_usd")
    @classmethod
    def max_cost_must_be_finite_and_non_negative(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value) or value < 0:
            raise ValueError("max_cost_usd must be finite and non-negative.")
        return value


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


class RoleBoundaryDecision(BaseModel):
    task_id: str
    role: str
    allowed: bool
    reason: str
    violating_paths: list[str] = Field(default_factory=list)
    suggested_owner_role: str | None = None


class OrchestrationBlocker(BaseModel):
    id: str
    task_id: str
    reason: str
    severity: str = "blocked"
    status: Literal["open", "resolved"] = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution: str | None = None


class OrchestrationFollowUp(BaseModel):
    id: str
    task_id: str
    assigned_role: str
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrchestrationTask(BaseModel):
    id: str
    title: str
    description: str
    role: str
    dependencies: list[str] = Field(default_factory=list)
    declared_write_paths: list[str] = Field(default_factory=list)
    shared_memory_tags: list[str] = Field(default_factory=list)
    expected_output: str = ""
    validation: str = ""
    retry_limit: int = Field(default=0, ge=0, le=10)
    retry_count: int = Field(default=0, ge=0)
    status: StepStatus = StepStatus.pending
    agent_id: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    completed_at: datetime | None = None


class OrchestrationTaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    role: str = Field(min_length=1, max_length=120)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    declared_write_paths: list[str] = Field(default_factory=list, max_length=20)
    shared_memory_tags: list[str] = Field(default_factory=list, max_length=20)
    expected_output: str = Field(default="", max_length=2000)
    validation: str = Field(default="", max_length=2000)
    retry_limit: int = Field(default=0, ge=0, le=10)


class OrchestrationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    tasks: list[OrchestrationTaskSpec] = Field(min_length=1, max_length=50)
    required_dod_evidence: list[str] = Field(default_factory=lambda: ["tests", "docs", "review"])
    shared_memory_tags: list[str] = Field(default_factory=list, max_length=20)
    shared_memory_policy: Literal["owner", "run"] = "owner"
    requested_by: str | None = None


class OrchestrationTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StepStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class OrchestrationTaskRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(min_length=1, max_length=2000)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    declared_write_paths: list[str] | None = Field(default=None, max_length=20)
    reset_retry_count: bool = False

    @field_validator("resolution")
    @classmethod
    def resolution_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("resolution must not be blank.")
        return stripped


class OrchestrationBlockerResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(min_length=1, max_length=2000)
    reschedule: bool = False

    @field_validator("resolution")
    @classmethod
    def resolution_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("resolution must not be blank.")
        return stripped


class OrchestrationCloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: dict[str, str] = Field(default_factory=dict)


class OrchestrationActionDecision(BaseModel):
    allowed: bool
    reason: str
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    violating_paths: list[str] = Field(default_factory=list)


class OrchestrationRun(BaseModel):
    id: str
    objective: str
    status: PlanStatus = PlanStatus.running
    tasks: list[OrchestrationTask]
    required_dod_evidence: list[str] = Field(default_factory=list)
    dod_evidence: dict[str, str] = Field(default_factory=dict)
    role_boundary_decisions: list[RoleBoundaryDecision] = Field(default_factory=list)
    blockers: list[OrchestrationBlocker] = Field(default_factory=list)
    follow_ups: list[OrchestrationFollowUp] = Field(default_factory=list)
    scheduled_task_ids: list[str] = Field(default_factory=list)
    shared_memory_tags: list[str] = Field(default_factory=list)
    shared_memory_policy: Literal["owner", "run"] = "owner"
    requested_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class OrchestrationLoopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(default=10, ge=1, le=50)
    stop_on_blocked: bool = True


class OrchestrationLoopResult(BaseModel):
    run: OrchestrationRun
    iterations: int = Field(ge=0)
    made_progress: bool
    stopped_reason: Literal[
        "waiting_for_agents",
        "blocked",
        "all_tasks_completed",
        "quiescent",
        "max_iterations",
        "cancelled",
    ]
    running_task_ids: list[str] = Field(default_factory=list)
    pending_task_ids: list[str] = Field(default_factory=list)
    unresolved_blocker_ids: list[str] = Field(default_factory=list)


class OrchestrationExecution(BaseModel):
    id: str
    run_id: str
    status: OrchestrationExecutionStatus = OrchestrationExecutionStatus.starting
    request: OrchestrationLoopRequest
    result: OrchestrationLoopResult | None = None
    requested_by: str | None = None
    supervisor_id: str | None = None
    scheduler_lease_id: str | None = None
    status_reason: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None


class OrchestrationOperationsSummary(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_runs: int = Field(ge=0)
    run_status_counts: dict[str, int] = Field(default_factory=dict)
    task_status_counts: dict[str, int] = Field(default_factory=dict)
    execution_status_counts: dict[str, int] = Field(default_factory=dict)
    active_execution_count: int = Field(ge=0)
    stale_execution_count: int = Field(ge=0)
    unresolved_blocker_count: int = Field(ge=0)
    open_follow_up_count: int = Field(ge=0)
    blocked_run_ids: list[str] = Field(default_factory=list)
    active_execution_ids: list[str] = Field(default_factory=list)
    stale_execution_ids: list[str] = Field(default_factory=list)


class OrchestrationDocumentSyncResult(BaseModel):
    progress_path: str
    backlog_path: str
    run_count: int = Field(ge=0)
    open_follow_up_count: int = Field(ge=0)
    unresolved_blocker_count: int = Field(ge=0)


class ToolManifest(BaseModel):
    name: str
    version: str = "0.2.6"
    description: str
    entrypoint: str
    permission_mode: PermissionMode
    tags: list[str] = Field(default_factory=list)
    interface: dict[str, Any] = Field(default_factory=dict)
    dependency_paths: list[str] = Field(default_factory=list)
    status: ToolStatus = ToolStatus.active
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    reliability_score: float = Field(default=1.0, ge=0.0, le=1.0)
    last_used_at: datetime | None = None
    deprecated_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("dependency_paths")
    @classmethod
    def dependency_paths_must_be_tool_local(cls, values: list[str]) -> list[str]:
        return _validate_tool_dependency_paths(values)


class ToolGenerationRequest(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    description: str = Field(min_length=1)
    trigger_source: ToolTriggerSource
    permission_mode: PermissionMode = PermissionMode.approval_required
    tags: list[str] = Field(default_factory=list)
    version: str = "0.2.6"
    source_code: str | None = None
    interface: dict[str, Any] = Field(default_factory=dict)
    dependency_paths: list[str] = Field(default_factory=list)
    overwrite: bool = False

    @field_validator("dependency_paths")
    @classmethod
    def dependency_paths_must_be_tool_local(cls, values: list[str]) -> list[str]:
        return _validate_tool_dependency_paths(values)


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
    approval_id: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None


FileAction = Literal[
    "read",
    "write",
    "binary_read",
    "binary_write",
    "delete",
    "move",
    "copy",
    "rename",
    "list",
    "metadata",
]


class AgentActionContext(BaseModel):
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None


class FileAccessRequest(AgentActionContext):
    path: Path
    action: FileAction
    target_path: Path | None = None


class FileAccessDecision(BaseModel):
    path: Path
    resolved_path: Path
    target_path: Path | None = None
    resolved_target_path: Path | None = None
    allowed: bool
    permission_mode: PermissionMode
    reason: str
    orchestration: OrchestrationActionDecision | None = None


class FileReadRequest(AgentActionContext):
    path: Path


class FileReadResponse(BaseModel):
    path: Path
    content: str
    bytes_read: int


class FileWriteRequest(AgentActionContext):
    path: Path
    content: str
    create_parent_dirs: bool = True


class FileWriteResponse(BaseModel):
    path: Path
    bytes_written: int


class FileBinaryReadRequest(AgentActionContext):
    path: Path


class FileBinaryReadResponse(BaseModel):
    path: Path
    content_base64: str
    bytes_read: int


class FileBinaryWriteRequest(AgentActionContext):
    path: Path
    content_base64: str
    create_parent_dirs: bool = True


class FileDeleteRequest(AgentActionContext):
    path: Path
    recursive: bool = False
    approved: bool = False


class FileDeleteResponse(BaseModel):
    path: Path
    deleted: bool


class FileMoveRequest(AgentActionContext):
    path: Path
    target_path: Path
    overwrite: bool = False
    approved: bool = False


class FileMoveResponse(BaseModel):
    path: Path
    target_path: Path
    moved: bool


class FileCopyRequest(AgentActionContext):
    path: Path
    target_path: Path
    overwrite: bool = False
    recursive: bool = False
    approved: bool = False


class FileCopyResponse(BaseModel):
    path: Path
    target_path: Path
    copied: bool
    bytes_copied: int | None = None


class FileRenameRequest(AgentActionContext):
    path: Path
    new_name: str
    overwrite: bool = False
    approved: bool = False

    @field_validator("new_name")
    @classmethod
    def new_name_must_be_single_path_segment(cls, value: str) -> str:
        candidate = Path(value)
        if not value.strip() or candidate.name != value or candidate.parent != Path("."):
            raise ValueError("new_name must be a single path segment.")
        return value


class FileRenameResponse(BaseModel):
    path: Path
    target_path: Path
    renamed: bool


class FileMetadataRequest(AgentActionContext):
    path: Path


class FileMetadataResponse(BaseModel):
    path: Path
    type: Literal["file", "directory", "other"]
    size_bytes: int | None = None
    modified_at: datetime
    is_symlink: bool = False


class FileListRequest(AgentActionContext):
    path: Path = Field(default_factory=lambda: Path("."))


class FileListEntry(FileMetadataResponse):
    name: str


class FileListResponse(BaseModel):
    path: Path
    entries: list[FileListEntry]


class CommandPolicyRequest(BaseModel):
    command: str
    cwd: Path | None = None
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
    orchestration: OrchestrationActionDecision | None = None


class CommandExecutionRequest(BaseModel):
    command: str
    cwd: Path | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    approved: bool = False
    approval_id: str | None = None
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
