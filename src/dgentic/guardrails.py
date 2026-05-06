from dgentic.events import event_log
from dgentic.schemas import (
    CommandPolicyDecision,
    CommandPolicyRequest,
    CommandRisk,
    FileAccessDecision,
    FileAccessRequest,
    LogEventType,
    PermissionMode,
)
from dgentic.settings import get_settings

BLOCKED_COMMANDS = {
    "format",
    "mkfs",
    "shutdown",
    "restart-computer",
    "remove-item",
    "rm",
    "rmdir",
    "del",
}
APPROVAL_COMMANDS = {"git", "pip", "uv", "npm", "pnpm", "yarn", "python", "powershell"}


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


def evaluate_command_policy(request: CommandPolicyRequest) -> CommandPolicyDecision:
    command = request.command.strip()
    executable = command.split()[0].lower()

    if executable in BLOCKED_COMMANDS:
        decision = CommandPolicyDecision(
            command=command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason=f"{executable} is blocked by the command policy.",
        )
    elif executable in APPROVAL_COMMANDS:
        decision = CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason=f"{executable} can change runtime or project state and needs approval.",
        )
    else:
        decision = CommandPolicyDecision(
            command=command,
            risk=CommandRisk.safe,
            permission_mode=PermissionMode.autopilot_safe,
            reason="Command is classified as read-only or low risk.",
        )

    event_log.record(
        LogEventType.cli,
        "Evaluated CLI command policy.",
        metadata=decision.model_dump(),
    )
    return decision
