from dgentic.command_policy import evaluate_command_policy as evaluate_configured_command_policy
from dgentic.events import event_log
from dgentic.schemas import (
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
    LogEventType,
    PermissionMode,
)
from dgentic.settings import get_settings


def evaluate_file_access(request: FileAccessRequest) -> FileAccessDecision:
    settings = get_settings()
    root_dir = settings.root_dir.resolve()
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = root_dir / data_dir
    protected_data_dir = data_dir.resolve()
    candidate = request.path
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    resolved = candidate.resolve()
    allowed = resolved == root_dir or root_dir in resolved.parents

    if not allowed:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            allowed=False,
            permission_mode=PermissionMode.blocked,
            reason=f"Path resolves outside configured rootDir: {root_dir}",
        )
    elif resolved == protected_data_dir or protected_data_dir in resolved.parents:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            allowed=False,
            permission_mode=PermissionMode.blocked,
            reason="DGentic state files are protected from guarded filesystem access.",
        )
    elif request.action == "delete":
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            allowed=False,
            permission_mode=PermissionMode.approval_required,
            reason="Delete operations require explicit approval.",
        )
    else:
        decision = FileAccessDecision(
            path=request.path,
            resolved_path=resolved,
            allowed=True,
            permission_mode=PermissionMode.autopilot_safe,
            reason="Path is inside rootDir and action is allowed.",
        )

    event_log.record(
        LogEventType.filesystem,
        "Evaluated filesystem access policy.",
        metadata=decision.model_dump(mode="json"),
    )
    return decision


def read_guarded_text_file(request: FileReadRequest) -> FileReadResponse:
    decision = evaluate_file_access(FileAccessRequest(path=request.path, action="read"))
    if not decision.allowed:
        raise PermissionError(decision.reason)
    if not decision.resolved_path.exists():
        raise FileNotFoundError(str(decision.path))
    if not decision.resolved_path.is_file():
        raise IsADirectoryError(str(decision.path))

    content = decision.resolved_path.read_text(encoding="utf-8")
    response = FileReadResponse(
        path=decision.path,
        content=content,
        bytes_read=len(content.encode("utf-8")),
    )
    event_log.record(
        LogEventType.filesystem,
        "Read guarded text file.",
        metadata={"path": str(decision.path), "bytes_read": response.bytes_read},
    )
    return response


def write_guarded_text_file(request: FileWriteRequest) -> FileWriteResponse:
    decision = evaluate_file_access(FileAccessRequest(path=request.path, action="write"))
    if not decision.allowed:
        raise PermissionError(decision.reason)

    if request.create_parent_dirs:
        decision.resolved_path.parent.mkdir(parents=True, exist_ok=True)
    elif not decision.resolved_path.parent.exists():
        raise FileNotFoundError(str(decision.resolved_path.parent))

    decision.resolved_path.write_text(request.content, encoding="utf-8")
    response = FileWriteResponse(
        path=decision.path,
        bytes_written=len(request.content.encode("utf-8")),
    )
    event_log.record(
        LogEventType.filesystem,
        "Wrote guarded text file.",
        metadata={"path": str(decision.path), "bytes_written": response.bytes_written},
    )
    return response


def evaluate_command_policy(request: CommandPolicyRequest) -> CommandPolicyDecision:
    return evaluate_configured_command_policy(request)


def execute_guarded_command(request: CommandExecutionRequest) -> CommandExecutionResult:
    from dgentic.cli_runtime import cli_runtime_service

    return cli_runtime_service.execute_command(request)
