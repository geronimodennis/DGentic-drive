import subprocess
from collections.abc import Iterable, Iterator
from itertools import chain

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from dgentic.agents import (
    get_agent,
    list_agents,
    list_child_agents,
    reconcile_outputs,
    spawn_agent,
    update_agent_status,
)
from dgentic.cli_runtime import (
    CommandApproval,
    CommandApprovalReview,
    CommandApprovalStatus,
    CommandRun,
    CommandRunOutput,
    cli_runtime_service,
)
from dgentic.command_policy import (
    create_command_policy_rule,
    list_command_policy_rules,
    update_command_policy_rule,
)
from dgentic.events import event_log
from dgentic.execution import execution_engine
from dgentic.guardrails import (
    copy_guarded_path,
    delete_guarded_path,
    evaluate_command_policy,
    evaluate_file_access,
    get_guarded_path_metadata,
    list_guarded_directory,
    move_guarded_path,
    read_guarded_binary_file,
    read_guarded_text_file,
    rename_guarded_path,
    write_guarded_binary_file,
    write_guarded_text_file,
)
from dgentic.memory import add_memory, search_memory
from dgentic.orchestration import OrchestrationError, orchestration_service
from dgentic.planner import create_initial_plan, list_plans
from dgentic.provider_pricing import ProviderPricingConfigurationError
from dgentic.provider_routing import ProviderRoutingConfigurationError
from dgentic.provider_runtime import (
    ProviderApproval,
    ProviderApprovalRequiredError,
    ProviderApprovalReview,
    ProviderApprovalStatus,
    ProviderConfigurationError,
    ProviderEgressPolicyError,
    ProviderFeatureNotSupportedError,
    ProviderGenerationRequest,
    ProviderGenerationResult,
    ProviderRateLimitError,
    ProviderStreamEvent,
    approve_provider_approval,
    create_provider_approval,
    deny_provider_approval,
    generate_provider_completion,
    get_provider_approval_review,
    list_provider_approvals,
    stream_provider_completion,
)
from dgentic.providers import (
    ProviderRoutingError,
    check_provider_health,
    choose_provider,
    list_providers,
)
from dgentic.schemas import (
    AgentBrief,
    AgentOutput,
    AgentReconciliation,
    AgentStatusUpdate,
    CommandApprovalDecisionRequest,
    CommandExecutionRequest,
    CommandExecutionResult,
    CommandPolicyDecision,
    CommandPolicyRequest,
    CommandPolicyRule,
    CommandPolicyRuleRequest,
    CommandPolicyRuleUpdate,
    FileAccessDecision,
    FileAccessRequest,
    FileBinaryReadRequest,
    FileBinaryReadResponse,
    FileBinaryWriteRequest,
    FileCopyRequest,
    FileCopyResponse,
    FileDeleteRequest,
    FileDeleteResponse,
    FileListRequest,
    FileListResponse,
    FileMetadataRequest,
    FileMetadataResponse,
    FileMoveRequest,
    FileMoveResponse,
    FileReadRequest,
    FileReadResponse,
    FileRenameRequest,
    FileRenameResponse,
    FileWriteRequest,
    FileWriteResponse,
    HealthResponse,
    LogEvent,
    LogEventType,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    OrchestrationBlockerResolutionRequest,
    OrchestrationCloseRequest,
    OrchestrationCreateRequest,
    OrchestrationRun,
    OrchestrationTaskRecoveryRequest,
    OrchestrationTaskUpdate,
    ProviderConfig,
    ProviderHealth,
    RoutingDecision,
    RoutingRequest,
    SessionSummary,
    TaskPlan,
    TaskRequest,
    TaskRun,
    ToolExecutionRequest,
    ToolGenerationRequest,
    ToolGenerationResult,
    ToolGovernanceUpdate,
    ToolManifest,
)
from dgentic.sessions import create_session_summary, list_session_summaries
from dgentic.settings import get_settings
from dgentic.tool_runtime import (
    ToolApproval,
    ToolApprovalReview,
    ToolApprovalStatus,
    ToolExecutionResult,
    approve_tool_approval,
    create_tool_approval,
    deny_tool_approval,
    execute_tool,
    get_tool_approval_review,
    list_tool_approvals,
)
from dgentic.tools import (
    ToolVersionConflictError,
    generate_tool,
    list_tools,
    register_tool,
    update_tool_governance,
)

router = APIRouter()


def _approval_decider(http_request: Request, requested_decider: str | None) -> str | None:
    principal = getattr(http_request.state, "principal", None)
    if principal is not None:
        return principal.token_id
    return requested_decider


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


@router.post("/tasks/orchestrations", response_model=OrchestrationRun, status_code=201)
def create_orchestration_run(
    payload: OrchestrationCreateRequest,
    request: Request,
) -> OrchestrationRun:
    try:
        return orchestration_service.create_run(
            payload,
            actor=_orchestration_actor(request),
        )
    except OrchestrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/orchestrations", response_model=list[OrchestrationRun])
def get_orchestration_runs(request: Request) -> list[OrchestrationRun]:
    return orchestration_service.list_runs(
        actor=_orchestration_actor(request),
        include_all=_orchestration_include_all(request),
    )


@router.get("/tasks/orchestrations/{run_id}", response_model=OrchestrationRun)
def get_orchestration_run(run_id: str, request: Request) -> OrchestrationRun:
    try:
        return _require_orchestration_run(run_id, request)
    except OrchestrationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/orchestrations/{run_id}/advance", response_model=OrchestrationRun)
def advance_orchestration_run(run_id: str, request: Request) -> OrchestrationRun:
    try:
        return orchestration_service.advance_run(
            run_id,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.post("/tasks/orchestrations/{run_id}/cycle", response_model=OrchestrationRun)
def run_orchestration_cycle(run_id: str, request: Request) -> OrchestrationRun:
    try:
        return orchestration_service.run_cycle(
            run_id,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.patch(
    "/tasks/orchestrations/{run_id}/tasks/{task_id}",
    response_model=OrchestrationRun,
)
def update_orchestration_task(
    run_id: str,
    task_id: str,
    update: OrchestrationTaskUpdate,
    request: Request,
) -> OrchestrationRun:
    try:
        return orchestration_service.update_task(
            run_id,
            task_id,
            update,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.post(
    "/tasks/orchestrations/{run_id}/tasks/{task_id}/recover",
    response_model=OrchestrationRun,
)
def recover_orchestration_task(
    run_id: str,
    task_id: str,
    payload: OrchestrationTaskRecoveryRequest,
    request: Request,
) -> OrchestrationRun:
    try:
        return orchestration_service.recover_task(
            run_id,
            task_id,
            payload,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.post(
    "/tasks/orchestrations/{run_id}/blockers/{blocker_id}/resolve",
    response_model=OrchestrationRun,
)
def resolve_orchestration_blocker(
    run_id: str,
    blocker_id: str,
    payload: OrchestrationBlockerResolutionRequest,
    request: Request,
) -> OrchestrationRun:
    _require_orchestration_admin(request)
    try:
        return orchestration_service.resolve_blocker(
            run_id,
            blocker_id,
            payload,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.post("/tasks/orchestrations/{run_id}/close", response_model=OrchestrationRun)
def close_orchestration_run(
    run_id: str,
    payload: OrchestrationCloseRequest,
    request: Request,
) -> OrchestrationRun:
    try:
        return orchestration_service.close_run(
            run_id,
            payload,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


def _require_orchestration_run(run_id: str, request: Request) -> OrchestrationRun:
    run = orchestration_service.get_run(
        run_id,
        actor=_orchestration_actor(request),
        include_all=_orchestration_include_all(request),
    )
    if run is None:
        raise OrchestrationError(f"Orchestration not found: {run_id}")
    return run


def _orchestration_http_error(exc: OrchestrationError) -> HTTPException:
    message = str(exc)
    status_code = 404 if "not found" in message.lower() else 400
    return HTTPException(status_code=status_code, detail=message)


def _orchestration_actor(request: Request) -> str | None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return None
    return principal.token_id


def _orchestration_include_all(request: Request) -> bool:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return True
    return bool(set(principal.capabilities) & {"admin", "*"})


def _require_orchestration_admin(request: Request) -> None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return
    if not set(principal.capabilities) & {"admin", "*"}:
        raise HTTPException(
            status_code=403,
            detail="Bearer token lacks the required capability.",
        )


@router.post("/guardrails/filesystem", response_model=FileAccessDecision)
def check_filesystem_access(request: FileAccessRequest) -> FileAccessDecision:
    return evaluate_file_access(request)


@router.post("/filesystem/read", response_model=FileReadResponse)
def read_file(request: FileReadRequest) -> FileReadResponse:
    try:
        return read_guarded_text_file(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/write", response_model=FileWriteResponse)
def write_file(request: FileWriteRequest) -> FileWriteResponse:
    try:
        return write_guarded_text_file(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/read-binary", response_model=FileBinaryReadResponse)
def read_binary_file(request: FileBinaryReadRequest) -> FileBinaryReadResponse:
    try:
        return read_guarded_binary_file(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/write-binary", response_model=FileWriteResponse)
def write_binary_file(request: FileBinaryWriteRequest) -> FileWriteResponse:
    try:
        return write_guarded_binary_file(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 413 if "maximum filesystem payload size" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/delete", response_model=FileDeleteResponse)
def delete_file(request: FileDeleteRequest) -> FileDeleteResponse:
    try:
        return delete_guarded_path(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/filesystem/move", response_model=FileMoveResponse)
def move_file(request: FileMoveRequest) -> FileMoveResponse:
    try:
        return move_guarded_path(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/copy", response_model=FileCopyResponse)
def copy_file(request: FileCopyRequest) -> FileCopyResponse:
    try:
        return copy_guarded_path(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IsADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/filesystem/rename", response_model=FileRenameResponse)
def rename_file(request: FileRenameRequest) -> FileRenameResponse:
    try:
        return rename_guarded_path(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/metadata", response_model=FileMetadataResponse)
def get_file_metadata(request: FileMetadataRequest) -> FileMetadataResponse:
    try:
        return get_guarded_path_metadata(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/list", response_model=FileListResponse)
def list_directory(request: FileListRequest) -> FileListResponse:
    try:
        return list_guarded_directory(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/guardrails/commands", response_model=CommandPolicyDecision)
def check_command_policy(request: CommandPolicyRequest) -> CommandPolicyDecision:
    return evaluate_command_policy(request)


@router.post("/cli/policy/rules", response_model=CommandPolicyRule, status_code=201)
def create_cli_policy_rule(request: CommandPolicyRuleRequest) -> CommandPolicyRule:
    return create_command_policy_rule(request)


@router.get("/cli/policy/rules", response_model=list[CommandPolicyRule])
def get_cli_policy_rules() -> list[CommandPolicyRule]:
    return list_command_policy_rules()


@router.patch("/cli/policy/rules/{rule_id}", response_model=CommandPolicyRule)
def patch_cli_policy_rule(
    rule_id: str,
    update: CommandPolicyRuleUpdate,
) -> CommandPolicyRule:
    rule = update_command_policy_rule(rule_id, update)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Command policy rule not found: {rule_id}")
    return rule


@router.post("/cli/execute", response_model=CommandExecutionResult)
def execute_command(request: CommandExecutionRequest) -> CommandExecutionResult:
    try:
        return cli_runtime_service.execute_command(request)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=408, detail="Command timed out.") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/runs", response_model=CommandRun, status_code=202)
def start_cli_run(request: CommandExecutionRequest) -> CommandRun:
    try:
        return cli_runtime_service.start_command(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cli/runs/{run_id}", response_model=CommandRun)
def get_cli_run(run_id: str) -> CommandRun:
    run = cli_runtime_service.get_command_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Command run not found: {run_id}")
    return run


@router.get("/cli/runs/{run_id}/output", response_model=CommandRunOutput)
def get_cli_run_output(run_id: str, after_sequence: int = 0) -> CommandRunOutput:
    try:
        return cli_runtime_service.get_command_run_output(
            run_id,
            after_sequence=after_sequence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/runs/{run_id}/cancel", response_model=CommandRun)
def cancel_cli_run(run_id: str) -> CommandRun:
    try:
        return cli_runtime_service.cancel_command_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cli/approvals", response_model=CommandApproval, status_code=201)
def create_cli_approval(
    request: CommandExecutionRequest,
    requested_by: str | None = None,
) -> CommandApproval:
    try:
        return cli_runtime_service.create_approval(request, requested_by=requested_by)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cli/approvals", response_model=list[CommandApproval])
def get_cli_approvals(status: CommandApprovalStatus | None = None) -> list[CommandApproval]:
    return cli_runtime_service.list_approvals(status)


@router.get("/cli/approvals/{approval_id}/review", response_model=CommandApprovalReview)
def get_cli_approval_review(approval_id: str) -> CommandApprovalReview:
    try:
        return cli_runtime_service.get_approval_review(approval_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/cli/approvals/{approval_id}/approve", response_model=CommandApproval)
def approve_cli_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> CommandApproval:
    try:
        return cli_runtime_service.approve_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cli/approvals/{approval_id}/deny", response_model=CommandApproval)
def deny_cli_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> CommandApproval:
    try:
        return cli_runtime_service.deny_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cli/approvals/{approval_id}/execute", response_model=CommandExecutionResult)
def execute_cli_approval(approval_id: str) -> CommandExecutionResult:
    try:
        return cli_runtime_service.execute_approved_command(approval_id)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=408, detail="Command timed out.") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/cli/runs", response_model=list[CommandRun])
def get_cli_runs() -> list[CommandRun]:
    return cli_runtime_service.list_command_runs()


@router.get("/providers", response_model=list[ProviderConfig])
def get_providers() -> list[ProviderConfig]:
    try:
        return list_providers()
    except ProviderPricingConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Provider pricing catalog is invalid.") from exc


@router.get("/providers/{provider_id}/health", response_model=ProviderHealth)
def get_provider_health(provider_id: str) -> ProviderHealth:
    try:
        return check_provider_health(provider_id)
    except ProviderPricingConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Provider pricing catalog is invalid.") from exc


@router.post("/providers/{provider_id}/approvals", response_model=ProviderApproval, status_code=201)
def create_external_provider_approval(
    provider_id: str,
    request: ProviderGenerationRequest,
    requested_by: str | None = None,
) -> ProviderApproval:
    try:
        return create_provider_approval(provider_id, request, requested_by=requested_by)
    except ProviderEgressPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/providers/approvals", response_model=list[ProviderApproval])
def get_external_provider_approvals(
    status: ProviderApprovalStatus | None = None,
) -> list[ProviderApproval]:
    return list_provider_approvals(status)


@router.get("/providers/approvals/{approval_id}/review", response_model=ProviderApprovalReview)
def get_external_provider_approval_review(approval_id: str) -> ProviderApprovalReview:
    try:
        return get_provider_approval_review(approval_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/providers/approvals/{approval_id}/approve", response_model=ProviderApproval)
def approve_external_provider_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> ProviderApproval:
    try:
        return approve_provider_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/providers/approvals/{approval_id}/deny", response_model=ProviderApproval)
def deny_external_provider_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> ProviderApproval:
    try:
        return deny_provider_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/routing/decide", response_model=RoutingDecision)
def decide_route(request: RoutingRequest) -> RoutingDecision:
    try:
        return choose_provider(request)
    except ProviderPricingConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Provider pricing catalog is invalid.") from exc
    except ProviderRoutingConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Provider role routing is invalid.") from exc
    except ProviderRoutingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/providers/generate", response_model=ProviderGenerationResult)
def generate_with_provider(request: ProviderGenerationRequest) -> ProviderGenerationResult:
    try:
        return generate_provider_completion(request)
    except ProviderEgressPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderApprovalRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderFeatureNotSupportedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRateLimitError as exc:
        raise HTTPException(status_code=429, detail="Provider request failed.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail="Provider request failed.") from exc


@router.post("/providers/generate/stream")
def stream_with_provider(request: ProviderGenerationRequest) -> StreamingResponse:
    try:
        events = stream_provider_completion(request)
        try:
            first_event = next(events)
        except StopIteration:
            stream_events = iter(())
        else:
            stream_events = chain([first_event], events)
        return StreamingResponse(
            _provider_stream_lines(stream_events),
            media_type="application/x-ndjson",
        )
    except ProviderEgressPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderApprovalRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderFeatureNotSupportedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRateLimitError as exc:
        raise HTTPException(status_code=429, detail="Provider request failed.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail="Provider request failed.") from exc


def _provider_stream_lines(events: Iterable[ProviderStreamEvent]) -> Iterator[str]:
    for event in events:
        yield event.model_dump_json() + "\n"


@router.post("/agents", response_model=AgentBrief, status_code=201)
def create_agent(brief: AgentBrief) -> AgentBrief:
    return spawn_agent(brief)


@router.get("/agents", response_model=list[AgentBrief])
def get_agents() -> list[AgentBrief]:
    return list_agents()


@router.get("/agents/{agent_id}", response_model=AgentBrief)
def get_agent_detail(agent_id: str) -> AgentBrief:
    agent = get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent


@router.get("/agents/{agent_id}/children", response_model=list[AgentBrief])
def get_child_agents(agent_id: str) -> list[AgentBrief]:
    return list_child_agents(agent_id)


@router.patch("/agents/{agent_id}/status", response_model=AgentBrief)
def update_agent_lifecycle_status(agent_id: str, update: AgentStatusUpdate) -> AgentBrief:
    agent = update_agent_status(agent_id, update)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent


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


@router.post("/tools/generate", response_model=ToolGenerationResult, status_code=201)
def generate_local_tool(request: ToolGenerationRequest) -> ToolGenerationResult:
    try:
        return generate_tool(request)
    except (FileExistsError, ToolVersionConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/tools", response_model=list[ToolManifest])
def get_tools() -> list[ToolManifest]:
    return list_tools()


@router.post("/tools/{name}/approvals", response_model=ToolApproval, status_code=201)
def create_local_tool_approval(
    name: str,
    request: ToolExecutionRequest,
    requested_by: str | None = None,
) -> ToolApproval:
    try:
        return create_tool_approval(name, request, requested_by=requested_by)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/tools/approvals", response_model=list[ToolApproval])
def get_local_tool_approvals(
    status: ToolApprovalStatus | None = None,
) -> list[ToolApproval]:
    return list_tool_approvals(status)


@router.get("/tools/approvals/{approval_id}/review", response_model=ToolApprovalReview)
def get_local_tool_approval_review(approval_id: str) -> ToolApprovalReview:
    try:
        return get_tool_approval_review(approval_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tools/approvals/{approval_id}/approve", response_model=ToolApproval)
def approve_local_tool_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> ToolApproval:
    try:
        return approve_tool_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/tools/approvals/{approval_id}/deny", response_model=ToolApproval)
def deny_local_tool_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> ToolApproval:
    try:
        return deny_tool_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/tools/{name}/execute", response_model=ToolExecutionResult)
def execute_local_tool(name: str, request: ToolExecutionRequest) -> ToolExecutionResult:
    try:
        return execute_tool(
            name,
            request.payload,
            approved=request.approved,
            approval_id=request.approval_id,
            timeout_seconds=request.timeout_seconds,
            requested_by=request.requested_by,
            agent_id=request.agent_id,
            agent_role=request.agent_role,
            task_id=request.task_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/tools/{name}/governance", response_model=ToolManifest)
def update_local_tool_governance(name: str, update: ToolGovernanceUpdate) -> ToolManifest:
    tool = update_tool_governance(name, update)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    return tool


@router.post("/sessions/summary", response_model=SessionSummary, status_code=201)
def create_summary(summary: SessionSummary) -> SessionSummary:
    return create_session_summary(summary)


@router.get("/sessions/summary", response_model=list[SessionSummary])
def get_summaries() -> list[SessionSummary]:
    return list_session_summaries()


@router.get("/logs", response_model=list[LogEvent])
def get_logs(event_type: LogEventType | None = None) -> list[LogEvent]:
    return event_log.list(event_type)
