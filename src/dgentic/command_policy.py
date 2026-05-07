import shlex
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dgentic.events import event_log
from dgentic.schemas import (
    CommandPolicyDecision,
    CommandPolicyMatchType,
    CommandPolicyRequest,
    CommandPolicyRule,
    CommandPolicyRuleRequest,
    CommandPolicyRuleUpdate,
    CommandRisk,
    LogEventType,
    PermissionMode,
)
from dgentic.storage import JsonCollection

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
APPROVAL_COMMANDS = {
    "git",
    "git.exe",
    "pip",
    "pip.exe",
    "uv",
    "uv.exe",
    "npm",
    "npm.cmd",
    "pnpm",
    "pnpm.cmd",
    "yarn",
    "yarn.cmd",
    "python",
    "python.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
}
SHELL_COMMAND_FLAGS = {
    "cmd": {"/c"},
    "cmd.exe": {"/c"},
    "sh": {"-c"},
    "bash": {"-c"},
    "powershell": {"-command", "-c"},
    "powershell.exe": {"-command", "-c"},
    "pwsh": {"-command", "-c"},
    "pwsh.exe": {"-command", "-c"},
}

_rules = JsonCollection("cli-command-policy-rules", CommandPolicyRule)


def create_command_policy_rule(request: CommandPolicyRuleRequest) -> CommandPolicyRule:
    rule = CommandPolicyRule(
        id=f"cmdpolicy-{uuid4()}",
        name=request.name,
        match_type=request.match_type,
        pattern=request.pattern,
        permission_mode=request.permission_mode,
        reason=request.reason,
        enabled=request.enabled,
        priority=request.priority,
    )
    _rules.upsert(rule)
    event_log.record(
        LogEventType.cli,
        "Created CLI command policy rule.",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )
    return rule


def list_command_policy_rules() -> list[CommandPolicyRule]:
    return _sorted_rules(_rules.list())


def update_command_policy_rule(
    rule_id: str,
    update: CommandPolicyRuleUpdate,
) -> CommandPolicyRule | None:
    rule = _rules.get(rule_id)
    if rule is None:
        return None

    updates = update.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(UTC)
    _rules.upsert(rule)
    event_log.record(
        LogEventType.cli,
        "Updated CLI command policy rule.",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )
    return rule


def evaluate_command_policy(request: CommandPolicyRequest) -> CommandPolicyDecision:
    command = request.command.strip()
    parsed = parse_command(command)

    for rule in _sorted_rules(_rules.list()):
        if not rule.enabled:
            continue
        if _rule_matches(rule, command, parsed):
            decision = _decision_from_rule(command, rule)
            _record_decision(decision)
            return decision

    decision = _default_decision(command, parsed)
    _record_decision(decision)
    return decision


class ParsedCommand:
    def __init__(self, executable: str, arguments: list[str]) -> None:
        self.executable = executable
        self.arguments = arguments


def parse_command(command: str) -> ParsedCommand:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        parts = command.split()
    if not parts:
        return ParsedCommand(executable="", arguments=[])

    executable = _normalize_executable(parts[0])
    return ParsedCommand(executable=executable, arguments=parts[1:])


def _normalize_executable(token: str) -> str:
    token = token.strip().strip("\"'")
    name = Path(token).name or token
    return name.lower()


def _sorted_rules(rules: list[CommandPolicyRule]) -> list[CommandPolicyRule]:
    return sorted(rules, key=lambda rule: (rule.priority, rule.created_at, rule.id))


def _rule_matches(rule: CommandPolicyRule, command: str, parsed: ParsedCommand) -> bool:
    pattern = rule.pattern.lower()
    normalized_command = " ".join(command.lower().split())

    if rule.match_type == CommandPolicyMatchType.executable:
        return parsed.executable == _normalize_executable(pattern)
    if rule.match_type == CommandPolicyMatchType.exact:
        return normalized_command == " ".join(pattern.split())
    if rule.match_type == CommandPolicyMatchType.contains:
        return pattern in command.lower()
    if rule.match_type == CommandPolicyMatchType.argument_contains:
        return any(pattern in argument.lower() for argument in parsed.arguments)
    return False


def _decision_from_rule(command: str, rule: CommandPolicyRule) -> CommandPolicyDecision:
    return CommandPolicyDecision(
        command=command,
        risk=_risk_for_permission(rule.permission_mode),
        permission_mode=rule.permission_mode,
        reason=rule.reason,
        matched_rule_id=rule.id,
        matched_rule_name=rule.name,
    )


def _default_decision(command: str, parsed: ParsedCommand) -> CommandPolicyDecision:
    executable = parsed.executable
    inner = _parse_inner_shell_command(parsed)
    if inner is not None:
        inner_decision = _default_decision(command, inner)
        if inner_decision.permission_mode == PermissionMode.blocked:
            inner_decision.reason = (
                f"Inner shell command {inner.executable} is blocked by the command policy."
            )
        elif inner_decision.permission_mode == PermissionMode.approval_required:
            inner_decision.reason = (
                f"Inner shell command {inner.executable} requires approval by the command policy."
            )
        return inner_decision

    if executable in SHELL_COMMAND_FLAGS:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason=f"{executable} requires approval when no inspectable inner command is present.",
        )
    if executable in BLOCKED_COMMANDS:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason=f"{executable} is blocked by the command policy.",
        )
    if executable in APPROVAL_COMMANDS:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason=f"{executable} can change runtime or project state and needs approval.",
        )
    return CommandPolicyDecision(
        command=command,
        risk=CommandRisk.safe,
        permission_mode=PermissionMode.autopilot_safe,
        reason="Command is classified as read-only or low risk.",
    )


def _parse_inner_shell_command(parsed: ParsedCommand) -> ParsedCommand | None:
    flags = SHELL_COMMAND_FLAGS.get(parsed.executable)
    if flags is None:
        return None

    for index, argument in enumerate(parsed.arguments):
        if argument.strip().strip("\"'").lower() in flags and index + 1 < len(parsed.arguments):
            inner_command = " ".join(parsed.arguments[index + 1 :]).strip().strip("\"'")
            if inner_command:
                return parse_command(inner_command)
    return None


def _risk_for_permission(permission_mode: PermissionMode) -> CommandRisk:
    if permission_mode == PermissionMode.blocked:
        return CommandRisk.blocked
    if permission_mode == PermissionMode.approval_required:
        return CommandRisk.approval_required
    return CommandRisk.safe


def _record_decision(decision: CommandPolicyDecision) -> None:
    event_log.record(
        LogEventType.cli,
        "Evaluated CLI command policy.",
        metadata=decision.model_dump(mode="json"),
    )
