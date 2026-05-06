"""Core types and data structures for DGentic."""
from typing import Any, Dict, List, Optional, Set
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Agent role types."""
    ORCHESTRATOR = "orchestrator"
    PLANNER = "planner"
    CODER = "coder"
    RESEARCHER = "researcher"
    VALIDATOR = "validator"
    GENERAL = "general"


class ModelType(str, Enum):
    """AI Model types."""
    LOCAL = "local"
    OPENAI = "openai"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PermissionLevel(str, Enum):
    """Action permission levels."""
    AUTOPILOT = "autopilot"
    APPROVAL_REQUIRED = "approval_required"


class ActionType(str, Enum):
    """Types of actions agents can perform."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    CLI_EXECUTE = "cli_execute"
    WEB_SEARCH = "web_search"
    WEB_SCRAPE = "web_scrape"
    CODE_EXECUTE = "code_execute"
    API_CALL = "api_call"
    TOOL_CREATE = "tool_create"
    AGENT_SPAWN = "agent_spawn"


class Task(BaseModel):
    """Task definition."""
    id: str
    title: str
    description: str
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    subtasks: List['Task'] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    required_data: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class Agent(BaseModel):
    """Agent definition."""
    id: str
    name: str
    role: AgentRole
    description: str
    model_type: ModelType = ModelType.LOCAL
    model_name: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    max_concurrent_tasks: int = 5
    timeout_seconds: int = 300
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolDefinition(BaseModel):
    """Tool definition."""
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    source_path: str
    metadata_path: str
    permission_level: PermissionLevel
    safe: bool = False
    reliability_score: float = 0.0
    usage_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    deprecated: bool = False


class Memory(BaseModel):
    """Memory entry."""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    category: str
    relevance_score: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    accessed_at: datetime = Field(default_factory=datetime.utcnow)
    usage_count: int = 0


class SkillDefinition(BaseModel):
    """Skill definition."""
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    source_path: str
    tags: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowStep(BaseModel):
    """Workflow step definition."""
    id: str
    name: str
    description: str
    agent_role: Optional[AgentRole] = None
    tool_name: Optional[str] = None
    previous_steps: List[str] = Field(default_factory=list)
    parallel_execution: bool = False
    error_handling: str = "fail"  # fail, retry, skip


class Workflow(BaseModel):
    """Workflow definition."""
    id: str
    name: str
    description: str
    steps: List[WorkflowStep] = Field(default_factory=list)
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(BaseModel):
    """Audit log entry."""
    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_id: str
    action_type: ActionType
    target: str  # file path, command, etc.
    status: str  # success, failed
    details: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None


# Update forward references
Task.model_rebuild()
