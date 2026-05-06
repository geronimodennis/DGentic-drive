import subprocess

from fastapi import APIRouter, HTTPException

from dgentic.agents import list_agents, reconcile_outputs, spawn_agent
from dgentic.events import event_log
from dgentic.execution import execution_engine
from dgentic.guardrails import (
    evaluate_command_policy,
    evaluate_file_access,
    execute_guarded_command,
    read_guarded_text_file,
    write_guarded_text_file,
)
from dgentic.memory import add_memory, search_memory
from dgentic.planner import create_initial_plan, list_plans
from dgentic.providers import check_provider_health, choose_provider, list_providers
from dgentic.schemas import (
    AgentBrief,
    AgentOutput,
    AgentReconciliation,
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandPolicyDecision,
    CommandPolicyRequest,
    FileAccessDecision,
    FileAccessRequest,
    FileReadRequest,
    FileReadResponse,
    FileWriteRequest,
    FileWriteResponse,
    HealthResponse,
    LogEvent,
    LogEventType,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    ProviderConfig,
    ProviderHealth,
    RoutingDecision,
    RoutingRequest,
    SessionSummary,
    TaskPlan,
    TaskRequest,
    TaskRun,
    ToolManifest,
)
from dgentic.sessions import create_session_summary, list_session_summaries
from dgentic.settings import get_settings
from dgentic.tools import list_tools, register_tool

router = APIRouter()


@router.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
    )


@router.post("/tasks/plan", response_model=TaskPlan, status_code=201)
def plan_task(request: TaskRequest) -> TaskPlan:
    return create_initial_plan(request)


@router.get("/tasks/plans", response_model=list[TaskPlan])
def get_task_plans() -> list[TaskPlan]:
    return list_plans()


@router.post("/tasks/execute", response_model=TaskRun, status_code=201)
def execute_task_plan(plan: TaskPlan) -> TaskRun:
    return execution_engine.execute_plan(plan)


@router.get("/tasks/runs", response_model=list[TaskRun])
def get_task_runs() -> list[TaskRun]:
    return execution_engine.list_runs()


@router.post("/guardrails/filesystem", response_model=FileAccessDecision)
def check_filesystem_access(request: FileAccessRequest) -> FileAccessDecision:
    return evaluate_file_access(request)


@router.post("/filesystem/read", response_model=FileReadResponse)
def read_file(request: FileReadRequest) -> FileReadResponse:
    try:
        return read_guarded_text_file(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/write", response_model=FileWriteResponse)
def write_file(request: FileWriteRequest) -> FileWriteResponse:
    try:
        return write_guarded_text_file(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/guardrails/commands", response_model=CommandPolicyDecision)
def check_command_policy(request: CommandPolicyRequest) -> CommandPolicyDecision:
    return evaluate_command_policy(request)


@router.post("/cli/execute", response_model=CommandExecutionResult)
def execute_command(request: CommandExecutionRequest) -> CommandExecutionResult:
    try:
        return execute_guarded_command(request)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=408, detail="Command timed out.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/providers", response_model=list[ProviderConfig])
def get_providers() -> list[ProviderConfig]:
    return list_providers()


@router.get("/providers/{provider_id}/health", response_model=ProviderHealth)
def get_provider_health(provider_id: str) -> ProviderHealth:
    return check_provider_health(provider_id)


@router.post("/routing/decide", response_model=RoutingDecision)
def decide_route(request: RoutingRequest) -> RoutingDecision:
    return choose_provider(request)


@router.post("/agents", response_model=AgentBrief, status_code=201)
def create_agent(brief: AgentBrief) -> AgentBrief:
    return spawn_agent(brief)


@router.get("/agents", response_model=list[AgentBrief])
def get_agents() -> list[AgentBrief]:
    return list_agents()


@router.post("/agents/reconcile", response_model=AgentReconciliation)
def reconcile_agent_outputs(outputs: list[AgentOutput]) -> AgentReconciliation:
    return reconcile_outputs(outputs)


@router.post("/memory", response_model=MemoryRecord, status_code=201)
def create_memory(record: MemoryRecord) -> MemoryRecord:
    return add_memory(record)


@router.post("/memory/search", response_model=list[MemorySearchResult])
def query_memory(query: MemoryQuery) -> list[MemorySearchResult]:
    return search_memory(query)


@router.post("/tools", response_model=ToolManifest, status_code=201)
def create_tool(manifest: ToolManifest) -> ToolManifest:
    return register_tool(manifest)


@router.get("/tools", response_model=list[ToolManifest])
def get_tools() -> list[ToolManifest]:
    return list_tools()


@router.post("/sessions/summary", response_model=SessionSummary, status_code=201)
def create_summary(summary: SessionSummary) -> SessionSummary:
    return create_session_summary(summary)


@router.get("/sessions/summary", response_model=list[SessionSummary])
def get_summaries() -> list[SessionSummary]:
    return list_session_summaries()


@router.get("/logs", response_model=list[LogEvent])
def get_logs(event_type: LogEventType | None = None) -> list[LogEvent]:
    return event_log.list(event_type)
