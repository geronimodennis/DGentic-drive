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
from dgentic.auth import (
    CAPABILITY_CLI,
    CAPABILITY_HOOKS,
    AuthTokenCreateResponse,
    AuthTokenRequest,
    AuthTokenRotateRequest,
    AuthTokenView,
    OperatorGroupRequest,
    OperatorGroupUpdateRequest,
    OperatorGroupView,
    OperatorRequest,
    OperatorUpdateRequest,
    OperatorView,
    create_auth_token,
    create_operator,
    create_operator_group,
    expire_auth_token,
    get_operator,
    get_operator_group,
    has_capability,
    list_auth_tokens,
    list_operator_groups,
    list_operators,
    revoke_auth_token,
    rotate_auth_token,
    update_operator,
    update_operator_group,
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
from dgentic.command_recipes import (
    CommandRecipe,
    CommandRecipeExecutionRequest,
    CommandRecipeExpansion,
    CommandRecipeRequest,
    CommandRecipeUpdate,
    build_command_recipe_request,
    create_command_recipe,
    expand_command_recipe,
    get_command_recipe,
    list_command_recipes,
    record_command_recipe_usage,
    update_command_recipe,
)
from dgentic.credentials import (
    CredentialReferenceError,
    CredentialReferenceRequest,
    CredentialReferenceView,
    CredentialVaultRotationRequest,
    CredentialVaultRotationResponse,
    create_credential_reference,
    list_credential_references,
    revoke_credential_reference,
    rotate_local_vault_credential_references,
)
from dgentic.events import event_log
from dgentic.execution import execution_engine
from dgentic.git_workflows import (
    GitCommitApprovalRequest,
    GitCommitRunRequest,
    GitCommitRunResult,
    GitPrApprovalRequest,
    GitPrRunRequest,
    GitPrRunResult,
    GitPushApprovalRequest,
    GitPushRunRequest,
    GitPushRunResult,
    GitWorkflowCheckpoint,
    GitWorkflowCheckpointRequest,
    build_git_commit_approval_request,
    build_git_pr_approval_request,
    build_git_push_approval_request,
    create_git_workflow_checkpoint,
    run_git_commit_workflow,
    run_git_pr_workflow,
    run_git_push_workflow,
)
from dgentic.guardrails import (
    FileApproval,
    FileApprovalRequiredError,
    FileApprovalReview,
    FileApprovalStatus,
    approve_file_approval,
    copy_guarded_path,
    create_file_approval,
    delete_guarded_path,
    deny_file_approval,
    evaluate_command_policy,
    evaluate_file_access,
    get_file_approval_review,
    get_guarded_path_metadata,
    list_file_approvals,
    list_guarded_directory,
    move_guarded_path,
    read_guarded_binary_file,
    read_guarded_text_file,
    rename_guarded_path,
    write_guarded_binary_file,
    write_guarded_text_file,
)
from dgentic.hook_policy import (
    create_hook_policy_rule,
    list_hook_policy_rules,
    update_hook_policy_rule,
)
from dgentic.memory import add_memory, search_memory
from dgentic.network_policy import (
    NetworkApproval,
    NetworkApprovalRequiredError,
    NetworkApprovalReview,
    NetworkApprovalStatus,
    NetworkDomainPolicyError,
    approve_network_approval,
    create_network_approval,
    deny_network_approval,
    evaluate_network_domain_policy,
    get_network_approval_review,
    list_network_approvals,
    safe_network_url_for_review,
)
from dgentic.orchestration import (
    OrchestrationContextAuthorizationError,
    OrchestrationError,
    orchestration_service,
)
from dgentic.planner import create_initial_plan, list_plans
from dgentic.plugins import (
    PluginCommandRecipeActivationResponse,
    PluginDiscoveryResponse,
    PluginDiscoveryView,
    PluginHookPolicyActivationResponse,
    PluginReferenceComponentActivationResponse,
    PluginReferenceComponentPreviewResponse,
    PluginTrustRequest,
    disable_plugin_command_recipe_activation,
    disable_plugin_hook_policy_activation,
    disable_plugin_reference_components,
    discover_plugins,
    get_plugin,
    install_plugin_command_recipes,
    install_plugin_hook_policies,
    install_plugin_reference_components,
    list_plugin_reference_components,
    preview_plugin_command_recipe_activation,
    preview_plugin_hook_policy_activation,
    preview_plugin_reference_components,
    update_plugin_trust,
)
from dgentic.projects import (
    ActiveProjectResponse,
    ProjectPreflightRequest,
    ProjectPreflightResponse,
    ProjectRecord,
    ProjectRequest,
    ProjectUpdateRequest,
    create_project,
    get_active_project,
    get_project,
    list_projects,
    preflight_project_root,
    update_project,
)
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
from dgentic.redaction import redact_sensitive_values
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
    FileApprovalRequest,
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
    HookPolicyRule,
    HookPolicyRuleRequest,
    HookPolicyRuleUpdate,
    LogEvent,
    LogEventType,
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
    NetworkApprovalRequest,
    NetworkPolicyDecision,
    NetworkPolicyRequest,
    OrchestrationBlockerResolutionRequest,
    OrchestrationCloseRequest,
    OrchestrationCreateRequest,
    OrchestrationExecution,
    OrchestrationLoopRequest,
    OrchestrationLoopResult,
    OrchestrationOperationsSummary,
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
    WebRetrievalFetchRequest,
    WebRetrievalFetchResponse,
    WebRetrievalNetworkRequest,
)
from dgentic.sessions import create_session_summary, list_session_summaries
from dgentic.settings import (
    EffectiveSettingsView,
    get_effective_settings_view,
    get_settings,
    require_managed_policy_surface_mutable,
)
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
from dgentic.web_retrieval import (
    WebRetrievalFetchError,
    WebRetrievalRedirectError,
    authorize_web_retrieval_network_request,
    create_web_retrieval_network_approval,
    evaluate_web_retrieval_network_policy,
    fetch_web_retrieval_url,
)

router = APIRouter()


def _approval_decider(http_request: Request, requested_decider: str | None) -> str | None:
    principal = getattr(http_request.state, "principal", None)
    if principal is not None:
        return principal.actor_id
    return requested_decider


def _principal_actor(request: Request) -> str | None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return None
    return principal.actor_id


def _approval_requester(http_request: Request, requested_by: str | None) -> str | None:
    return _principal_actor(http_request) or requested_by


def _bind_principal_requester(payload, http_request: Request):
    actor = _principal_actor(http_request)
    if actor is None:
        return payload
    return payload.model_copy(update={"requested_by": actor})


def _require_authenticated_capability(request: Request, capability: str) -> None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return
    if not has_capability(principal, capability):
        raise HTTPException(
            status_code=403,
            detail="Bearer token lacks the required capability.",
        )


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


@router.get("/settings/effective", response_model=EffectiveSettingsView)
def get_effective_runtime_settings() -> EffectiveSettingsView:
    return get_effective_settings_view()


@router.post("/projects/preflight", response_model=ProjectPreflightResponse)
def preflight_project(payload: ProjectPreflightRequest) -> ProjectPreflightResponse:
    try:
        return preflight_project_root(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects", response_model=list[ProjectRecord])
def get_projects() -> list[ProjectRecord]:
    return list_projects()


@router.post("/projects", response_model=ProjectRecord, status_code=201)
def register_project(payload: ProjectRequest, request: Request) -> ProjectRecord:
    try:
        return create_project(payload, actor=_principal_actor(request))
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "already" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.get("/projects/active", response_model=ActiveProjectResponse)
def get_runtime_active_project() -> ActiveProjectResponse:
    return get_active_project()


@router.get("/projects/{project_id}", response_model=ProjectRecord)
def get_registered_project(project_id: str) -> ProjectRecord:
    try:
        return get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/projects/{project_id}", response_model=ProjectRecord)
def update_registered_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    request: Request,
) -> ProjectRecord:
    try:
        return update_project(project_id, payload, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/auth/tokens", response_model=AuthTokenCreateResponse, status_code=201)
def create_persisted_auth_token(
    payload: AuthTokenRequest,
    request: Request,
) -> AuthTokenCreateResponse:
    try:
        return create_auth_token(payload, actor=_principal_actor(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/auth/tokens", response_model=list[AuthTokenView])
def get_persisted_auth_tokens() -> list[AuthTokenView]:
    return list_auth_tokens()


@router.post("/auth/operator-groups", response_model=OperatorGroupView, status_code=201)
def create_persisted_operator_group(
    payload: OperatorGroupRequest,
    request: Request,
) -> OperatorGroupView:
    try:
        return create_operator_group(payload, actor=_principal_actor(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/auth/operator-groups", response_model=list[OperatorGroupView])
def get_persisted_operator_groups() -> list[OperatorGroupView]:
    return list_operator_groups()


@router.get("/auth/operator-groups/{group_id}", response_model=OperatorGroupView)
def get_persisted_operator_group(group_id: str) -> OperatorGroupView:
    try:
        return get_operator_group(group_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/auth/operator-groups/{group_id}", response_model=OperatorGroupView)
def update_persisted_operator_group(
    group_id: str,
    payload: OperatorGroupUpdateRequest,
    request: Request,
) -> OperatorGroupView:
    try:
        return update_operator_group(group_id, payload, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/auth/operators", response_model=OperatorView, status_code=201)
def create_persisted_operator(
    payload: OperatorRequest,
    request: Request,
) -> OperatorView:
    try:
        return create_operator(payload, actor=_principal_actor(request))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/auth/operators", response_model=list[OperatorView])
def get_persisted_operators() -> list[OperatorView]:
    return list_operators()


@router.get("/auth/operators/{operator_id}", response_model=OperatorView)
def get_persisted_operator(operator_id: str) -> OperatorView:
    try:
        return get_operator(operator_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/auth/operators/{operator_id}", response_model=OperatorView)
def update_persisted_operator(
    operator_id: str,
    payload: OperatorUpdateRequest,
    request: Request,
) -> OperatorView:
    try:
        return update_operator(operator_id, payload, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/auth/tokens/{token_id}/rotate", response_model=AuthTokenCreateResponse)
def rotate_persisted_auth_token(
    token_id: str,
    payload: AuthTokenRotateRequest,
    request: Request,
) -> AuthTokenCreateResponse:
    try:
        return rotate_auth_token(token_id, payload, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/auth/tokens/{token_id}/revoke", response_model=AuthTokenView)
def revoke_persisted_auth_token(token_id: str, request: Request) -> AuthTokenView:
    try:
        return revoke_auth_token(token_id, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/auth/tokens/{token_id}/expire", response_model=AuthTokenView)
def expire_persisted_auth_token(token_id: str, request: Request) -> AuthTokenView:
    try:
        return expire_auth_token(token_id, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/credentials/references", response_model=CredentialReferenceView, status_code=201)
def create_persisted_credential_reference(
    payload: CredentialReferenceRequest,
    request: Request,
) -> CredentialReferenceView:
    try:
        return create_credential_reference(payload, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except CredentialReferenceError as exc:
        raise HTTPException(status_code=400, detail="Credential reference is invalid.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Credential reference is invalid.") from exc


@router.get("/credentials/references", response_model=list[CredentialReferenceView])
def get_persisted_credential_references() -> list[CredentialReferenceView]:
    return list_credential_references()


@router.post(
    "/credentials/references/local-vault/rotate-key",
    response_model=CredentialVaultRotationResponse,
)
def rotate_local_vault_credentials(
    payload: CredentialVaultRotationRequest,
    request: Request,
) -> CredentialVaultRotationResponse:
    try:
        return rotate_local_vault_credential_references(payload, actor=_principal_actor(request))
    except CredentialReferenceError as exc:
        raise HTTPException(status_code=400, detail="Credential vault rotation failed.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Credential vault rotation failed.") from exc


@router.post(
    "/credentials/references/{credential_ref_id}/revoke",
    response_model=CredentialReferenceView,
)
def revoke_persisted_credential_reference(
    credential_ref_id: str,
    request: Request,
) -> CredentialReferenceView:
    try:
        return revoke_credential_reference(credential_ref_id, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/plan", response_model=TaskPlan, status_code=201)
def plan_task(request: TaskRequest) -> TaskPlan:
    return create_initial_plan(request)


@router.get("/tasks/plans", response_model=list[TaskPlan])
def get_task_plans() -> list[TaskPlan]:
    return list_plans()


@router.post("/tasks/execute", response_model=TaskRun, status_code=201)
def execute_task_plan(plan: TaskPlan, request: Request) -> TaskRun:
    return execution_engine.execute_plan(plan, actor=_principal_actor(request))


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


@router.get(
    "/tasks/orchestrations/operations/summary",
    response_model=OrchestrationOperationsSummary,
)
def get_orchestration_operations_summary(request: Request) -> OrchestrationOperationsSummary:
    return orchestration_service.get_operations_summary(
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


@router.post("/tasks/orchestrations/{run_id}/loop", response_model=OrchestrationLoopResult)
def run_orchestration_loop(
    run_id: str,
    request: Request,
    payload: OrchestrationLoopRequest | None = None,
) -> OrchestrationLoopResult:
    loop_request = payload or OrchestrationLoopRequest()
    try:
        return orchestration_service.run_loop(
            run_id,
            loop_request,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.post(
    "/tasks/orchestrations/{run_id}/executions",
    response_model=OrchestrationExecution,
    status_code=202,
)
def start_orchestration_background_execution(
    run_id: str,
    request: Request,
    payload: OrchestrationLoopRequest | None = None,
) -> OrchestrationExecution:
    loop_request = payload or OrchestrationLoopRequest()
    try:
        return orchestration_service.start_background_execution(
            run_id,
            loop_request,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.get(
    "/tasks/orchestrations/{run_id}/executions",
    response_model=list[OrchestrationExecution],
)
def list_orchestration_background_executions(
    run_id: str,
    request: Request,
) -> list[OrchestrationExecution]:
    try:
        return orchestration_service.list_background_executions(
            run_id,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.get(
    "/tasks/orchestrations/{run_id}/executions/{execution_id}",
    response_model=OrchestrationExecution,
)
def get_orchestration_background_execution(
    run_id: str,
    execution_id: str,
    request: Request,
) -> OrchestrationExecution:
    try:
        return orchestration_service.get_background_execution(
            run_id,
            execution_id,
            actor=_orchestration_actor(request),
            include_all=_orchestration_include_all(request),
        )
    except OrchestrationError as exc:
        raise _orchestration_http_error(exc) from exc


@router.post(
    "/tasks/orchestrations/{run_id}/executions/{execution_id}/cancel",
    response_model=OrchestrationExecution,
)
def cancel_orchestration_background_execution(
    run_id: str,
    execution_id: str,
    request: Request,
) -> OrchestrationExecution:
    try:
        return orchestration_service.cancel_background_execution(
            run_id,
            execution_id,
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
    lowered = message.lower()
    if "not found" in lowered:
        status_code = 404
    elif (
        "already has active background execution" in lowered
        or "scheduler lease is active" in lowered
        or "changed during update" in lowered
        or "no longer active" in lowered
        or "is not active" in lowered
    ):
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=message)


def _orchestration_actor(request: Request) -> str | None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return None
    return principal.actor_id


def _orchestration_include_all(request: Request) -> bool:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return True
    return _principal_is_admin(request)


def _principal_is_admin(request: Request) -> bool:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return False
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


def _visible_agent_briefs(agents: list[AgentBrief], request: Request) -> list[AgentBrief]:
    (
        visible_agent_ids,
        orchestration_agent_ids,
    ) = orchestration_service.orchestration_agent_visibility(
        actor=_orchestration_actor(request), include_all=_orchestration_include_all(request)
    )
    return [
        agent
        for agent in agents
        if agent.id not in orchestration_agent_ids or agent.id in visible_agent_ids
    ]


def _agent_brief_is_visible(agent: AgentBrief, request: Request) -> bool:
    return agent in _visible_agent_briefs([agent], request)


@router.post("/guardrails/filesystem", response_model=FileAccessDecision)
def check_filesystem_access(payload: FileAccessRequest, request: Request) -> FileAccessDecision:
    return evaluate_file_access(payload, actor=_principal_actor(request))


@router.post("/filesystem/approvals", response_model=FileApproval, status_code=201)
def create_filesystem_approval(
    payload: FileApprovalRequest,
    request: Request,
) -> FileApproval:
    try:
        return create_file_approval(
            payload,
            requested_by=_approval_requester(request, payload.requested_by),
        )
    except (FileApprovalRequiredError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/filesystem/approvals", response_model=list[FileApproval])
def get_filesystem_approvals(
    status: FileApprovalStatus | None = None,
) -> list[FileApproval]:
    return list_file_approvals(status)


@router.get("/filesystem/approvals/{approval_id}/review", response_model=FileApprovalReview)
def review_filesystem_approval(approval_id: str) -> FileApprovalReview:
    try:
        return get_file_approval_review(approval_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/filesystem/approvals/{approval_id}/approve", response_model=FileApproval)
def approve_filesystem_approval(
    approval_id: str,
    decision: CommandApprovalDecisionRequest,
    request: Request,
) -> FileApproval:
    try:
        return approve_file_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/filesystem/approvals/{approval_id}/deny", response_model=FileApproval)
def deny_filesystem_approval(
    approval_id: str,
    decision: CommandApprovalDecisionRequest,
    request: Request,
) -> FileApproval:
    try:
        return deny_file_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/filesystem/read", response_model=FileReadResponse)
def read_file(payload: FileReadRequest, request: Request) -> FileReadResponse:
    try:
        return read_guarded_text_file(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 413 if "maximum filesystem payload size" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/write", response_model=FileWriteResponse)
def write_file(payload: FileWriteRequest, request: Request) -> FileWriteResponse:
    try:
        return write_guarded_text_file(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 413 if "maximum filesystem payload size" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/read-binary", response_model=FileBinaryReadResponse)
def read_binary_file(payload: FileBinaryReadRequest, request: Request) -> FileBinaryReadResponse:
    try:
        return read_guarded_binary_file(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 413 if "maximum filesystem payload size" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except (IsADirectoryError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/write-binary", response_model=FileWriteResponse)
def write_binary_file(payload: FileBinaryWriteRequest, request: Request) -> FileWriteResponse:
    try:
        return write_guarded_binary_file(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        status_code = 413 if "maximum filesystem payload size" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/delete", response_model=FileDeleteResponse)
def delete_file(payload: FileDeleteRequest, request: Request) -> FileDeleteResponse:
    try:
        return delete_guarded_path(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/filesystem/move", response_model=FileMoveResponse)
def move_file(payload: FileMoveRequest, request: Request) -> FileMoveResponse:
    try:
        return move_guarded_path(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/copy", response_model=FileCopyResponse)
def copy_file(payload: FileCopyRequest, request: Request) -> FileCopyResponse:
    try:
        return copy_guarded_path(payload, actor=_principal_actor(request))
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
def rename_file(payload: FileRenameRequest, request: Request) -> FileRenameResponse:
    try:
        return rename_guarded_path(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/metadata", response_model=FileMetadataResponse)
def get_file_metadata(payload: FileMetadataRequest, request: Request) -> FileMetadataResponse:
    try:
        return get_guarded_path_metadata(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/filesystem/list", response_model=FileListResponse)
def list_directory(payload: FileListRequest, request: Request) -> FileListResponse:
    try:
        return list_guarded_directory(payload, actor=_principal_actor(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/guardrails/commands", response_model=CommandPolicyDecision)
def check_command_policy(payload: CommandPolicyRequest, request: Request) -> CommandPolicyDecision:
    return evaluate_command_policy(payload, actor=_principal_actor(request))


@router.post("/guardrails/network", response_model=NetworkPolicyDecision)
def check_network_policy(
    request: NetworkPolicyRequest,
    http_request: Request,
) -> NetworkPolicyDecision:
    try:
        decision = evaluate_network_domain_policy(
            request.url,
            actor=_principal_actor(http_request),
        )
    except NetworkDomainPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NetworkPolicyDecision(
        allowed=decision.allowed,
        url=safe_network_url_for_review(decision.url),
        host=decision.host,
        mode=decision.mode,
        matched_domain=decision.matched_domain,
        matched_rule_id=decision.matched_rule_id,
        matched_rule_source=decision.matched_rule_source,
        reason=redact_sensitive_values(decision.reason),
        hook_policy=decision.hook_policy,
    )


@router.post("/network/approvals", response_model=NetworkApproval, status_code=201)
def create_network_policy_approval(
    payload: NetworkApprovalRequest,
    http_request: Request,
) -> NetworkApproval:
    try:
        return create_network_approval(
            payload.url,
            surface=payload.surface,
            action=payload.action,
            requested_by=_approval_requester(http_request, payload.requested_by),
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            task_id=payload.task_id,
        )
    except NetworkDomainPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OrchestrationContextAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/network/approvals", response_model=list[NetworkApproval])
def get_network_policy_approvals(
    status: NetworkApprovalStatus | None = None,
) -> list[NetworkApproval]:
    return list_network_approvals(status)


@router.get("/network/approvals/{approval_id}/review", response_model=NetworkApprovalReview)
def review_network_policy_approval(approval_id: str) -> NetworkApprovalReview:
    try:
        return get_network_approval_review(approval_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/network/approvals/{approval_id}/approve", response_model=NetworkApproval)
def approve_network_policy_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> NetworkApproval:
    try:
        return approve_network_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/network/approvals/{approval_id}/deny", response_model=NetworkApproval)
def deny_network_policy_approval(
    approval_id: str,
    request: Request,
    decision: CommandApprovalDecisionRequest,
) -> NetworkApproval:
    try:
        return deny_network_approval(
            approval_id,
            decided_by=_approval_decider(request, decision.decided_by),
            reason=decision.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/web-retrieval/network/check", response_model=NetworkPolicyDecision)
def check_web_retrieval_network_policy(
    payload: WebRetrievalNetworkRequest,
    http_request: Request,
) -> NetworkPolicyDecision:
    try:
        decision = evaluate_web_retrieval_network_policy(
            payload.url,
            actor=_principal_actor(http_request),
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            task_id=payload.task_id,
        )
    except NetworkDomainPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return NetworkPolicyDecision(
        allowed=decision.allowed,
        url=safe_network_url_for_review(decision.url),
        host=decision.host,
        mode=decision.mode,
        matched_domain=decision.matched_domain,
        matched_rule_id=decision.matched_rule_id,
        matched_rule_source=decision.matched_rule_source,
        reason=redact_sensitive_values(decision.reason),
        hook_policy=decision.hook_policy,
    )


@router.post(
    "/web-retrieval/network/approvals",
    response_model=NetworkApproval,
    status_code=201,
)
def create_web_retrieval_network_policy_approval(
    payload: WebRetrievalNetworkRequest,
    http_request: Request,
) -> NetworkApproval:
    try:
        return create_web_retrieval_network_approval(
            payload.url,
            requested_by=_approval_requester(http_request, payload.requested_by),
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            task_id=payload.task_id,
        )
    except NetworkDomainPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OrchestrationContextAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/web-retrieval/network/authorize", response_model=NetworkPolicyDecision)
def authorize_web_retrieval_network_policy(
    payload: WebRetrievalNetworkRequest,
    http_request: Request,
) -> NetworkPolicyDecision:
    try:
        decision = authorize_web_retrieval_network_request(
            payload.url,
            approval_id=payload.approval_id,
            requested_by=_approval_requester(http_request, payload.requested_by),
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            task_id=payload.task_id,
        )
    except NetworkDomainPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (NetworkApprovalRequiredError, OrchestrationContextAuthorizationError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return NetworkPolicyDecision(
        allowed=decision.allowed,
        url=safe_network_url_for_review(decision.url),
        host=decision.host,
        mode=decision.mode,
        matched_domain=decision.matched_domain,
        matched_rule_id=decision.matched_rule_id,
        matched_rule_source=decision.matched_rule_source,
        reason=redact_sensitive_values(decision.reason),
        hook_policy=decision.hook_policy,
    )


@router.post("/web-retrieval/fetch", response_model=WebRetrievalFetchResponse)
def fetch_web_retrieval_url_route(
    payload: WebRetrievalFetchRequest,
    http_request: Request,
) -> WebRetrievalFetchResponse:
    try:
        return fetch_web_retrieval_url(
            payload.url,
            approval_id=payload.approval_id,
            requested_by=_approval_requester(http_request, payload.requested_by),
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            task_id=payload.task_id,
            timeout_seconds=payload.timeout_seconds,
            max_response_bytes=payload.max_response_bytes,
        )
    except NetworkDomainPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (NetworkApprovalRequiredError, OrchestrationContextAuthorizationError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (PermissionError, WebRetrievalRedirectError) as exc:
        raise HTTPException(status_code=403, detail=redact_sensitive_values(str(exc))) from exc
    except WebRetrievalFetchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=redact_sensitive_values(str(exc)),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/policy/rules", response_model=CommandPolicyRule, status_code=201)
def create_cli_policy_rule(
    payload: CommandPolicyRuleRequest,
    request: Request,
) -> CommandPolicyRule:
    try:
        require_managed_policy_surface_mutable("cli_policy")
        return create_command_policy_rule(payload, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/cli/policy/rules", response_model=list[CommandPolicyRule])
def get_cli_policy_rules() -> list[CommandPolicyRule]:
    return list_command_policy_rules()


@router.patch("/cli/policy/rules/{rule_id}", response_model=CommandPolicyRule)
def patch_cli_policy_rule(
    rule_id: str,
    update: CommandPolicyRuleUpdate,
    request: Request,
) -> CommandPolicyRule:
    try:
        require_managed_policy_surface_mutable("cli_policy")
        rule = update_command_policy_rule(rule_id, update, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Command policy rule not found: {rule_id}")
    return rule


@router.post("/cli/recipes", response_model=CommandRecipe, status_code=201)
def create_cli_command_recipe(
    payload: CommandRecipeRequest,
    request: Request,
) -> CommandRecipe:
    try:
        require_managed_policy_surface_mutable("command_recipes")
        return create_command_recipe(payload, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/cli/recipes", response_model=list[CommandRecipe])
def get_cli_command_recipes() -> list[CommandRecipe]:
    return list_command_recipes()


@router.get("/cli/recipes/{recipe_id}", response_model=CommandRecipe)
def get_cli_command_recipe(recipe_id: str) -> CommandRecipe:
    try:
        return get_command_recipe(recipe_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/cli/recipes/{recipe_id}", response_model=CommandRecipe)
def patch_cli_command_recipe(
    recipe_id: str,
    payload: CommandRecipeUpdate,
    request: Request,
) -> CommandRecipe:
    try:
        require_managed_policy_surface_mutable("command_recipes")
        return update_command_recipe(recipe_id, payload, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/recipes/{recipe_id}/preview", response_model=CommandRecipeExpansion)
def preview_cli_command_recipe(
    recipe_id: str,
    payload: CommandRecipeExecutionRequest,
    request: Request,
) -> CommandRecipeExpansion:
    try:
        return expand_command_recipe(
            recipe_id,
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/recipes/{recipe_id}/execute", response_model=CommandExecutionResult)
def execute_cli_command_recipe(
    recipe_id: str,
    payload: CommandRecipeExecutionRequest,
    request: Request,
) -> CommandExecutionResult:
    try:
        command_request = build_command_recipe_request(
            recipe_id,
            _bind_principal_requester(payload, request),
        )
        result = cli_runtime_service.execute_command(command_request)
        record_command_recipe_usage(recipe_id, action="execute", actor=_principal_actor(request))
        return result
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


@router.post("/cli/recipes/{recipe_id}/approvals", response_model=CommandApproval, status_code=201)
def create_cli_command_recipe_approval(
    recipe_id: str,
    payload: CommandRecipeExecutionRequest,
    request: Request,
) -> CommandApproval:
    try:
        command_request = build_command_recipe_request(
            recipe_id,
            _bind_principal_requester(payload, request),
        )
        approval = cli_runtime_service.create_approval(
            command_request,
            requested_by=_approval_requester(request, command_request.requested_by),
        )
        record_command_recipe_usage(recipe_id, action="approval", actor=_principal_actor(request))
        return approval
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/recipes/{recipe_id}/runs", response_model=CommandRun, status_code=202)
def start_cli_command_recipe_run(
    recipe_id: str,
    payload: CommandRecipeExecutionRequest,
    request: Request,
) -> CommandRun:
    try:
        command_request = build_command_recipe_request(
            recipe_id,
            _bind_principal_requester(payload, request),
        )
        run = cli_runtime_service.start_command(command_request)
        record_command_recipe_usage(recipe_id, action="run", actor=_principal_actor(request))
        return run
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/checkpoints", response_model=GitWorkflowCheckpoint)
def create_cli_git_checkpoint(
    payload: GitWorkflowCheckpointRequest,
    request: Request,
) -> GitWorkflowCheckpoint:
    try:
        return create_git_workflow_checkpoint(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/commit-approvals", response_model=CommandApproval, status_code=201)
def create_cli_git_commit_approval(
    payload: GitCommitApprovalRequest,
    request: Request,
) -> CommandApproval:
    try:
        command_request = build_git_commit_approval_request(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
        return cli_runtime_service.create_approval(
            command_request,
            requested_by=_approval_requester(request, command_request.requested_by),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/commit-runs", response_model=GitCommitRunResult, status_code=201)
def run_cli_git_commit(
    payload: GitCommitRunRequest,
    request: Request,
) -> GitCommitRunResult:
    try:
        return run_git_commit_workflow(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/push-approvals", response_model=CommandApproval, status_code=201)
def create_cli_git_push_approval(
    payload: GitPushApprovalRequest,
    request: Request,
) -> CommandApproval:
    try:
        command_request = build_git_push_approval_request(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
        return cli_runtime_service.create_approval(
            command_request,
            requested_by=_approval_requester(request, command_request.requested_by),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/push-runs", response_model=GitPushRunResult, status_code=201)
def run_cli_git_push(
    payload: GitPushRunRequest,
    request: Request,
) -> GitPushRunResult:
    try:
        return run_git_push_workflow(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/pr-approvals", response_model=CommandApproval, status_code=201)
def create_cli_git_pr_approval(
    payload: GitPrApprovalRequest,
    request: Request,
) -> CommandApproval:
    try:
        command_request = build_git_pr_approval_request(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
        return cli_runtime_service.create_approval(
            command_request,
            requested_by=_approval_requester(request, command_request.requested_by),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/git/pr-runs", response_model=GitPrRunResult, status_code=201)
def run_cli_git_pr(
    payload: GitPrRunRequest,
    request: Request,
) -> GitPrRunResult:
    try:
        return run_git_pr_workflow(
            _bind_principal_requester(payload, request),
            actor=_principal_actor(request),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/guardrails/hooks/rules", response_model=HookPolicyRule, status_code=201)
def create_hook_policy(
    payload: HookPolicyRuleRequest,
    request: Request,
) -> HookPolicyRule:
    try:
        require_managed_policy_surface_mutable("hook_policy")
        return create_hook_policy_rule(payload, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/guardrails/hooks/rules", response_model=list[HookPolicyRule])
def get_hook_policies() -> list[HookPolicyRule]:
    return list_hook_policy_rules()


@router.patch("/guardrails/hooks/rules/{rule_id}", response_model=HookPolicyRule)
def patch_hook_policy(
    rule_id: str,
    update: HookPolicyRuleUpdate,
    request: Request,
) -> HookPolicyRule:
    try:
        require_managed_policy_surface_mutable("hook_policy")
        rule = update_hook_policy_rule(rule_id, update, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Hook policy rule not found.")
    return rule


@router.get("/plugins", response_model=PluginDiscoveryResponse)
def discover_local_plugins() -> PluginDiscoveryResponse:
    return discover_plugins()


@router.get("/plugins/{plugin_id}", response_model=PluginDiscoveryView)
def get_local_plugin(plugin_id: str) -> PluginDiscoveryView:
    try:
        return get_plugin(plugin_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/plugins/{plugin_id}/trust", response_model=PluginDiscoveryView)
def patch_local_plugin_trust(
    plugin_id: str,
    payload: PluginTrustRequest,
    request: Request,
) -> PluginDiscoveryView:
    try:
        require_managed_policy_surface_mutable("plugin_trust")
        return update_plugin_trust(plugin_id, payload, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/components/preview",
    response_model=PluginReferenceComponentPreviewResponse,
)
def preview_local_plugin_reference_components(
    plugin_id: str,
) -> PluginReferenceComponentPreviewResponse:
    try:
        return preview_plugin_reference_components(plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/components/install",
    response_model=PluginReferenceComponentActivationResponse,
)
def install_local_plugin_reference_components(
    plugin_id: str,
    request: Request,
) -> PluginReferenceComponentActivationResponse:
    try:
        require_managed_policy_surface_mutable("plugin_components")
        return install_plugin_reference_components(plugin_id, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/components/disable",
    response_model=PluginReferenceComponentActivationResponse,
)
def disable_local_plugin_reference_components(
    plugin_id: str,
    request: Request,
) -> PluginReferenceComponentActivationResponse:
    try:
        require_managed_policy_surface_mutable("plugin_components")
        return disable_plugin_reference_components(plugin_id, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/plugins/{plugin_id}/components",
    response_model=PluginReferenceComponentActivationResponse,
)
def list_local_plugin_reference_components(
    plugin_id: str,
) -> PluginReferenceComponentActivationResponse:
    try:
        return list_plugin_reference_components(plugin_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/command-recipes/preview",
    response_model=PluginCommandRecipeActivationResponse,
)
def preview_local_plugin_command_recipes(
    plugin_id: str,
    request: Request,
) -> PluginCommandRecipeActivationResponse:
    _require_authenticated_capability(request, CAPABILITY_CLI)
    try:
        return preview_plugin_command_recipe_activation(plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/command-recipes/install",
    response_model=PluginCommandRecipeActivationResponse,
)
def install_local_plugin_command_recipes(
    plugin_id: str,
    request: Request,
) -> PluginCommandRecipeActivationResponse:
    _require_authenticated_capability(request, CAPABILITY_CLI)
    try:
        require_managed_policy_surface_mutable("plugin_command_recipes")
        return install_plugin_command_recipes(plugin_id, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/command-recipes/disable",
    response_model=PluginCommandRecipeActivationResponse,
)
def disable_local_plugin_command_recipes(
    plugin_id: str,
    request: Request,
) -> PluginCommandRecipeActivationResponse:
    _require_authenticated_capability(request, CAPABILITY_CLI)
    try:
        require_managed_policy_surface_mutable("plugin_command_recipes")
        return disable_plugin_command_recipe_activation(plugin_id, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/hook-policies/preview",
    response_model=PluginHookPolicyActivationResponse,
)
def preview_local_plugin_hook_policies(
    plugin_id: str,
    request: Request,
) -> PluginHookPolicyActivationResponse:
    _require_authenticated_capability(request, CAPABILITY_HOOKS)
    try:
        return preview_plugin_hook_policy_activation(plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/hook-policies/install",
    response_model=PluginHookPolicyActivationResponse,
)
def install_local_plugin_hook_policies(
    plugin_id: str,
    request: Request,
) -> PluginHookPolicyActivationResponse:
    _require_authenticated_capability(request, CAPABILITY_HOOKS)
    try:
        require_managed_policy_surface_mutable("plugin_hook_policies")
        return install_plugin_hook_policies(plugin_id, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/plugins/{plugin_id}/hook-policies/disable",
    response_model=PluginHookPolicyActivationResponse,
)
def disable_local_plugin_hook_policies(
    plugin_id: str,
    request: Request,
) -> PluginHookPolicyActivationResponse:
    _require_authenticated_capability(request, CAPABILITY_HOOKS)
    try:
        require_managed_policy_surface_mutable("plugin_hook_policies")
        return disable_plugin_hook_policy_activation(plugin_id, actor=_principal_actor(request))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cli/execute", response_model=CommandExecutionResult)
def execute_command(
    payload: CommandExecutionRequest,
    request: Request,
) -> CommandExecutionResult:
    try:
        return cli_runtime_service.execute_command(_bind_principal_requester(payload, request))
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
def start_cli_run(
    payload: CommandExecutionRequest,
    request: Request,
) -> CommandRun:
    try:
        return cli_runtime_service.start_command(_bind_principal_requester(payload, request))
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
def cancel_cli_run(run_id: str, request: Request) -> CommandRun:
    try:
        return cli_runtime_service.cancel_command_run(run_id, actor=_principal_actor(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cli/approvals", response_model=CommandApproval, status_code=201)
def create_cli_approval(
    payload: CommandExecutionRequest,
    http_request: Request,
    requested_by: str | None = None,
) -> CommandApproval:
    try:
        return cli_runtime_service.create_approval(
            payload,
            requested_by=_approval_requester(http_request, requested_by),
        )
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
def execute_cli_approval(approval_id: str, request: Request) -> CommandExecutionResult:
    try:
        return cli_runtime_service.execute_approved_command(
            approval_id,
            actor=_principal_actor(request),
            allow_cross_actor=_principal_is_admin(request),
        )
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
    payload: ProviderGenerationRequest,
    http_request: Request,
    requested_by: str | None = None,
) -> ProviderApproval:
    try:
        return create_provider_approval(
            provider_id,
            payload,
            requested_by=_approval_requester(http_request, requested_by),
        )
    except ProviderEgressPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OrchestrationContextAuthorizationError as exc:
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
def generate_with_provider(
    payload: ProviderGenerationRequest,
    request: Request,
) -> ProviderGenerationResult:
    try:
        return generate_provider_completion(_bind_principal_requester(payload, request))
    except ProviderEgressPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProviderApprovalRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except OrchestrationContextAuthorizationError as exc:
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
def stream_with_provider(
    payload: ProviderGenerationRequest,
    request: Request,
) -> StreamingResponse:
    try:
        events = stream_provider_completion(_bind_principal_requester(payload, request))
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
    except OrchestrationContextAuthorizationError as exc:
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
def create_agent(brief: AgentBrief, request: Request) -> AgentBrief:
    return spawn_agent(brief, actor=_principal_actor(request))


@router.get("/agents", response_model=list[AgentBrief])
def get_agents(request: Request) -> list[AgentBrief]:
    return _visible_agent_briefs(list_agents(), request)


@router.get("/agents/{agent_id}", response_model=AgentBrief)
def get_agent_detail(agent_id: str, request: Request) -> AgentBrief:
    agent = get_agent(agent_id)
    if agent is None or not _agent_brief_is_visible(agent, request):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent


@router.get("/agents/{agent_id}/children", response_model=list[AgentBrief])
def get_child_agents(agent_id: str, request: Request) -> list[AgentBrief]:
    return _visible_agent_briefs(list_child_agents(agent_id), request)


@router.patch("/agents/{agent_id}/status", response_model=AgentBrief)
def update_agent_lifecycle_status(
    agent_id: str,
    update: AgentStatusUpdate,
    request: Request,
) -> AgentBrief:
    current = get_agent(agent_id)
    if current is None or not _agent_brief_is_visible(current, request):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    agent = update_agent_status(agent_id, update, actor=_principal_actor(request))
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return agent


@router.post("/agents/reconcile", response_model=AgentReconciliation)
def reconcile_agent_outputs(outputs: list[AgentOutput], request: Request) -> AgentReconciliation:
    return reconcile_outputs(outputs, actor=_principal_actor(request))


@router.post("/memory", response_model=MemoryRecord, status_code=201)
def create_memory(record: MemoryRecord, request: Request) -> MemoryRecord:
    return add_memory(record, actor=_principal_actor(request))


@router.post("/memory/search", response_model=list[MemorySearchResult])
def query_memory(query: MemoryQuery, request: Request) -> list[MemorySearchResult]:
    return search_memory(query, actor=_principal_actor(request))


@router.post("/tools", response_model=ToolManifest, status_code=201)
def create_tool(manifest: ToolManifest, request: Request) -> ToolManifest:
    return register_tool(manifest, actor=_principal_actor(request))


@router.post("/tools/generate", response_model=ToolGenerationResult, status_code=201)
def generate_local_tool(
    payload: ToolGenerationRequest,
    request: Request,
) -> ToolGenerationResult:
    try:
        return generate_tool(payload, actor=_principal_actor(request))
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
    payload: ToolExecutionRequest,
    http_request: Request,
    requested_by: str | None = None,
) -> ToolApproval:
    try:
        return create_tool_approval(
            name,
            payload,
            requested_by=_approval_requester(http_request, requested_by),
        )
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
def execute_local_tool(
    name: str,
    payload: ToolExecutionRequest,
    request: Request,
) -> ToolExecutionResult:
    try:
        return execute_tool(
            name,
            payload.payload,
            approved=payload.approved,
            approval_id=payload.approval_id,
            network_approval_id=payload.network_approval_id,
            timeout_seconds=payload.timeout_seconds,
            requested_by=_approval_requester(request, payload.requested_by),
            agent_id=payload.agent_id,
            agent_role=payload.agent_role,
            task_id=payload.task_id,
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
def update_local_tool_governance(
    name: str,
    update: ToolGovernanceUpdate,
    request: Request,
) -> ToolManifest:
    tool = update_tool_governance(name, update, actor=_principal_actor(request))
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool not found: {name}")
    return tool


@router.post("/sessions/summary", response_model=SessionSummary, status_code=201)
def create_summary(summary: SessionSummary, request: Request) -> SessionSummary:
    return create_session_summary(summary, actor=_principal_actor(request))


@router.get("/sessions/summary", response_model=list[SessionSummary])
def get_summaries() -> list[SessionSummary]:
    return list_session_summaries()


@router.get("/logs", response_model=list[LogEvent])
def get_logs(event_type: LogEventType | None = None) -> list[LogEvent]:
    return event_log.list(event_type)
