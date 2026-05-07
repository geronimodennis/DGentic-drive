import shlex
import subprocess
from datetime import UTC, datetime

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
    root_dir = get_settings().root_dir.resolve()
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
    decision = evaluate_command_policy(CommandPolicyRequest(command=request.command))
    if decision.permission_mode == PermissionMode.blocked:
        raise PermissionError(decision.reason)
    if decision.permission_mode == PermissionMode.approval_required and not request.approved:
        raise PermissionError("Command requires explicit approval before execution.")

    root_dir = get_settings().root_dir.resolve()
    cwd = request.cwd or root_dir
    if not cwd.is_absolute():
        cwd = root_dir / cwd
    cwd = cwd.resolve()
    if cwd != root_dir and root_dir not in cwd.parents:
        raise PermissionError(f"Command cwd resolves outside configured rootDir: {root_dir}")

    started_at = datetime.now(UTC)
    completed = subprocess.run(
        shlex.split(request.command, posix=False),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=request.timeout_seconds,
        check=False,
    )
    duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    result = CommandExecutionResult(
        command=request.command,
        cwd=cwd,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        permission_mode=decision.permission_mode,
        duration_ms=duration_ms,
    )
    event_log.record(
        LogEventType.cli,
        "Executed guarded CLI command.",
        metadata={
            "command": request.command,
            "cwd": str(cwd),
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "permission_mode": decision.permission_mode,
        },
    )
    return result
