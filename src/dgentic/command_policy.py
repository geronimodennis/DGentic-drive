from __future__ import annotations

import glob
import os
import re
import shlex
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from dgentic.events import event_log
from dgentic.orchestration import authorize_cli_action
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
from dgentic.settings import get_settings
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
    "erase",
    "rd",
    "ri",
}
WINDOWS_EXECUTABLE_EXTENSIONS = frozenset({".bat", ".cmd", ".com", ".exe"})
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
READ_ONLY_COMMANDS = {
    "cat",
    "dir",
    "echo",
    "get-childitem",
    "get-location",
    "hostname",
    "ls",
    "pwd",
    "type",
    "ver",
    "where",
    "which",
    "whoami",
    "write-host",
    "write-output",
}
READ_ONLY_PATH_COMMANDS = {
    "cat",
    "dir",
    "get-childitem",
    "ls",
    "type",
}
SHELL_COMMAND_FLAGS = {
    "cmd": {"/c", "/k"},
    "cmd.exe": {"/c", "/k"},
    "sh": {"-c"},
    "bash": {"-c"},
    "powershell": {"/c", "/command", "-command", "-c"},
    "powershell.exe": {"/c", "/command", "-command", "-c"},
    "pwsh": {"/c", "/command", "-command", "-c"},
    "pwsh.exe": {"/c", "/command", "-command", "-c"},
}
CMD_EXECUTABLES = frozenset({"cmd", "cmd.exe"})
POWERSHELL_EXECUTABLES = frozenset({"powershell", "powershell.exe", "pwsh", "pwsh.exe"})
SHELL_CONTROL_OPERATORS = frozenset({";", "&", "|", "\n"})
SHELL_STRUCTURAL_APPROVAL_TOKENS = frozenset({">", "<", "2>", ">>", "<<"})
SHELL_FLOW_COMMAND_TOKENS = frozenset(
    {
        "case",
        "catch",
        "do",
        "done",
        "elif",
        "else",
        "esac",
        "fi",
        "for",
        "foreach",
        "function",
        "if",
        "finally",
        "switch",
        "then",
        "trap",
        "try",
        "until",
        "while",
    }
)
SHELL_COMMAND_PREFIX_TOKENS = frozenset(
    {
        "!",
        "builtin",
        "call",
        "command",
        "doas",
        "env",
        "exec",
        "nice",
        "nohup",
        "setsid",
        "start",
        "start-process",
        "sudo",
        "time",
    }
)
SHELL_COMMAND_PREFIX_OPTIONS_WITH_VALUES = {
    "command": frozenset(),
    "doas": frozenset({"-c", "-u"}),
    "env": frozenset({"--chdir", "--ignore-signal", "--split-string", "--unset", "-c", "-s", "-u"}),
    "exec": frozenset({"-a"}),
    "nice": frozenset({"--adjustment", "-n"}),
    "nohup": frozenset(),
    "setsid": frozenset(),
    "start": frozenset(
        {
            "/affinity",
            "/d",
            "/node",
        }
    ),
    "start-process": frozenset(
        {
            "-args",
            "-argumentlist",
            "-credential",
            "-file-path",
            "-filepath",
            "-path",
            "-redirectstandarderror",
            "-redirectstandardinput",
            "-redirectstandardoutput",
            "-verb",
            "-windowstyle",
            "-workingdirectory",
        }
    ),
    "sudo": frozenset(
        {
            "--close-from",
            "--command-timeout",
            "--group",
            "--host",
            "--login-class",
            "--prompt",
            "--role",
            "--type",
            "--user",
            "-c",
            "-d",
            "-g",
            "-h",
            "-p",
            "-r",
            "-t",
            "-u",
        }
    ),
    "time": frozenset({"--format", "--output", "-f", "-o"}),
}
SHELL_COMMAND_APPROVAL_TOKENS = frozenset(
    {
        "builtin",
        "call",
        "command",
        "doas",
        "env",
        "eval",
        "exec",
        "iex",
        "invoke-expression",
        "nice",
        "nohup",
        "setsid",
        "source",
        "start",
        "start-process",
        "sudo",
        "time",
        *SHELL_FLOW_COMMAND_TOKENS,
    }
)
SHELL_APPROVAL_TOKENS = SHELL_STRUCTURAL_APPROVAL_TOKENS | SHELL_COMMAND_APPROVAL_TOKENS
SHELL_BLOCK_SCAN_COMMAND_TOKENS = SHELL_FLOW_COMMAND_TOKENS
START_PROCESS_ARGUMENT_LIST_OPTIONS = frozenset({"-args", "-argument-list", "-argumentlist"})
START_PROCESS_COMMAND_NAMES = frozenset({"saps", "start", "start-process"})
START_PROCESS_FILE_PATH_OPTIONS = frozenset({"-file-path", "-filepath", "-path"})
_SHELL_ASSIGNMENT_TOKEN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\+)?=.*$")
_LEADING_SHELL_ASSIGNMENT_RE = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*(?:\+)?="
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|(?:\\.|[^\s;&|'\"\)])+)\s+"
)
_SHELL_PATH_EXPANSION_RE = re.compile(
    r"\$(?:\{[^}\s]+\}|[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!_-]|['\"])"
)
_WINDOWS_PATH_EXPANSION_RE = re.compile(r"%[^%\s]+(?::[^%]*)?%|![^!\s]+(?::[^!]*)?!")
_ANSI_C_QUOTED_SEGMENT_RE = re.compile(r"\$'((?:\\.|[^'\\])*)'")
_LOCALIZED_QUOTED_SEGMENT_RE = re.compile(r'\$"((?:\\.|[^"\\])*)"')
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)"
    r"|TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)\s*=\s*"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\$\([^;&|]*?\)|`(?:\\.|[^`\\])*`|(?:(?:`[\s\S])|\\.|[^\s;&|'\"\)])+)",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_RE = re.compile(
    r"(?P<prefix>(?:--?|/)[A-Za-z0-9_-]*"
    r"(?:api[-_]?key|access[-_]?key|token|password|secret)[A-Za-z0-9_-]*"
    r"(?:\s+|=|:))"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|\$\([^;&|]*?\)|`(?:\\.|[^`\\])*`|(?:(?:`[\s\S])|\\.|[^\s;&|'\"\)])+)",
    re.IGNORECASE,
)
_SENSITIVE_ASSIGNMENT_PREFIX_RE = re.compile(
    r"\b(?:[A-Za-z_][A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)"
    r"|TOKEN|PASSWORD|SECRET|API_KEY|ACCESS_KEY)\s*=\s*",
    re.IGNORECASE,
)
_SENSITIVE_FLAG_PREFIX_RE = re.compile(
    r"(?P<prefix>(?:--?|/)[A-Za-z0-9_-]*"
    r"(?:api[-_]?key|access[-_]?key|token|password|secret)[A-Za-z0-9_-]*"
    r"(?:\s+|=|:))",
    re.IGNORECASE,
)
_rules = JsonCollection("cli-command-policy-rules", CommandPolicyRule)


def create_command_policy_rule(
    request: CommandPolicyRuleRequest,
    *,
    actor: str | None = None,
) -> CommandPolicyRule:
    rule = CommandPolicyRule(
        id=f"cmdpolicy-{uuid4()}",
        name=request.name,
        match_type=request.match_type,
        pattern=request.pattern,
        permission_mode=request.permission_mode,
        reason=request.reason,
        agent_roles=_normalize_agent_roles(request.agent_roles),
        enabled=request.enabled,
        priority=request.priority,
    )
    _rules.upsert(rule)
    event_log.record(
        LogEventType.cli,
        "Created CLI command policy rule.",
        actor=actor or "system",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )
    return rule


def list_command_policy_rules() -> list[CommandPolicyRule]:
    return _sorted_rules(_rules.list())


def update_command_policy_rule(
    rule_id: str,
    update: CommandPolicyRuleUpdate,
    *,
    actor: str | None = None,
) -> CommandPolicyRule | None:
    rule = _rules.get(rule_id)
    if rule is None:
        return None

    updates = update.model_dump(exclude_unset=True)
    if "agent_roles" in updates and updates["agent_roles"] is not None:
        updates["agent_roles"] = _normalize_agent_roles(updates["agent_roles"])
    for field, value in updates.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(UTC)
    _rules.upsert(rule)
    event_log.record(
        LogEventType.cli,
        "Updated CLI command policy rule.",
        actor=actor or "system",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )
    return rule


def evaluate_command_policy(
    request: CommandPolicyRequest,
    *,
    actor: str | None = None,
) -> CommandPolicyDecision:
    command = request.command.strip()
    parsed = parse_command(command)
    orchestration_decision = authorize_cli_action(
        agent_id=request.agent_id,
        agent_role=request.agent_role,
        task_id=request.task_id,
    )

    def finish(decision: CommandPolicyDecision) -> CommandPolicyDecision:
        decision = decision.model_copy(update={"orchestration": orchestration_decision})
        _record_decision(decision, actor=actor)
        return decision

    if not orchestration_decision.allowed:
        return finish(
            CommandPolicyDecision(
                command=command,
                risk=CommandRisk.blocked,
                permission_mode=PermissionMode.blocked,
                reason=orchestration_decision.reason,
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
        )

    policy_cwd = _resolve_policy_cwd(request.cwd)
    if policy_cwd is None:
        decision = CommandPolicyDecision(
            command=command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason="Command cwd resolves outside configured rootDir.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
        return finish(decision)

    default_decision = _default_decision(command, parsed, request, policy_cwd)

    if parsed.executable not in SHELL_COMMAND_FLAGS:
        if default_decision.permission_mode in {
            PermissionMode.blocked,
            PermissionMode.approval_required,
        } and (
            default_decision.permission_mode == PermissionMode.blocked
            or default_decision.reason
            == "Command references DGentic state files and needs approval."
        ):
            return finish(default_decision)
        decision = _decision_from_configured_rules(command, parsed, request)
        if decision is not None:
            return finish(decision)

    if parsed.executable in SHELL_COMMAND_FLAGS:
        wrapper_decision = default_decision
        if wrapper_decision.permission_mode == PermissionMode.blocked:
            return finish(wrapper_decision)

        configured_decision = _decision_from_configured_rules(command, parsed, request)
        if configured_decision is not None and (
            configured_decision.permission_mode == PermissionMode.blocked
        ):
            return finish(configured_decision)

        if wrapper_decision.permission_mode == PermissionMode.approval_required:
            return finish(wrapper_decision)

        if configured_decision is not None:
            return finish(configured_decision)

        return finish(wrapper_decision)

    decision = _default_decision(command, parsed, request, policy_cwd)
    return finish(decision)


def _decision_from_configured_rules(
    command: str,
    parsed: ParsedCommand,
    request: CommandPolicyRequest,
) -> CommandPolicyDecision | None:
    for rule in _sorted_rules(_rules.list()):
        if not rule.enabled:
            continue
        if not _rule_applies_to_context(rule, request):
            continue
        if _rule_matches(rule, command, parsed):
            return _decision_from_rule(command, rule, request)
    return None


class ParsedCommand:
    def __init__(
        self,
        executable: str,
        arguments: list[str],
        original_command: str = "",
        raw_executable: str | None = None,
    ) -> None:
        self.executable = executable
        self.arguments = arguments
        self.original_command = original_command
        self.raw_executable = raw_executable or executable


def parse_command(command: str) -> ParsedCommand:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        parts = command.split()
    if not parts:
        return ParsedCommand(executable="", arguments=[])

    raw_executable = _strip_matching_quotes(parts[0].strip())
    executable = _normalize_executable(raw_executable)
    return ParsedCommand(
        executable=executable,
        arguments=[_strip_matching_quotes(part) for part in parts[1:]],
        original_command=command,
        raw_executable=raw_executable,
    )


def parse_inner_shell_command(command: str) -> str | None:
    return _parse_inner_shell_command(parse_command(command))


def _normalize_executable(token: str) -> str:
    token = _strip_matching_quotes(token.strip())
    if "\\" in token or ":" in token:
        name = PureWindowsPath(token).name or token
    else:
        name = PurePosixPath(token).name or token
    return name.lower()


def _strip_matching_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


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


def _rule_applies_to_context(rule: CommandPolicyRule, request: CommandPolicyRequest) -> bool:
    if not rule.agent_roles:
        return True
    if request.agent_role is None:
        return False
    return request.agent_role.strip().lower() in rule.agent_roles


def _decision_from_rule(
    command: str,
    rule: CommandPolicyRule,
    request: CommandPolicyRequest,
) -> CommandPolicyDecision:
    return CommandPolicyDecision(
        command=command,
        risk=_risk_for_permission(rule.permission_mode),
        permission_mode=rule.permission_mode,
        reason=rule.reason,
        agent_role=request.agent_role,
        agent_id=request.agent_id,
        task_id=request.task_id,
        matched_rule_id=rule.id,
        matched_rule_name=rule.name,
    )


def _default_decision(
    command: str,
    parsed: ParsedCommand,
    request: CommandPolicyRequest,
    policy_cwd: Path,
    *,
    windows_command_context: bool | None = None,
) -> CommandPolicyDecision:
    if windows_command_context is None:
        windows_command_context = _host_is_windows()
    executable = parsed.executable
    blocked_executable = _blocked_command_name(executable)
    inner_command = _parse_inner_shell_command(parsed)
    if inner_command is not None:
        return _decision_for_inner_shell_command(
            command,
            inner_command,
            request,
            policy_cwd,
            windows_command_context=_host_is_windows() and parsed.executable in CMD_EXECUTABLES,
            powershell_command_context=parsed.executable in POWERSHELL_EXECUTABLES,
        )

    if executable in SHELL_COMMAND_FLAGS:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason=f"{executable} requires approval when no inspectable inner command is present.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    if _executable_path_targets_outside_root(
        parsed.raw_executable,
        policy_cwd,
        windows_command_context=windows_command_context,
        powershell_command_context=parsed.executable in POWERSHELL_EXECUTABLES,
    ):
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason="Command executable path resolves outside configured rootDir.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    if blocked_executable is not None:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason=f"{executable} is blocked by the command policy.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    if _command_targets_protected_data_dir(
        command,
        windows_command_context=windows_command_context,
        powershell_command_context=parsed.executable in POWERSHELL_EXECUTABLES,
    ):
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Command references DGentic state files and needs approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    if _read_only_command_targets_outside_root(
        parsed,
        policy_cwd,
        windows_command_context=windows_command_context,
    ):
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason=f"{executable} references a path outside configured rootDir.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    if executable in APPROVAL_COMMANDS:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason=f"{executable} can change runtime or project state and needs approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    if executable not in READ_ONLY_COMMANDS:
        return CommandPolicyDecision(
            command=command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason=f"{executable} is not explicitly classified as read-only and needs approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    return CommandPolicyDecision(
        command=command,
        risk=CommandRisk.safe,
        permission_mode=PermissionMode.autopilot_safe,
        reason="Command is classified as read-only or low risk.",
        agent_role=request.agent_role,
        agent_id=request.agent_id,
        task_id=request.task_id,
    )


def _decision_for_inner_shell_command(
    outer_command: str,
    inner_command: str,
    request: CommandPolicyRequest,
    policy_cwd: Path,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> CommandPolicyDecision:
    if _command_targets_protected_data_dir(
        inner_command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    ):
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Command references DGentic state files and needs approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    segments, has_control_operator = _split_shell_command_segments(
        inner_command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )
    substitutions = _extract_shell_substitutions(
        inner_command,
        powershell_command_context=powershell_command_context,
    )
    script_scan_decision = _decision_from_shell_script_tokens(
        outer_command,
        inner_command,
        request,
        policy_cwd,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )
    if script_scan_decision.permission_mode == PermissionMode.blocked:
        return script_scan_decision
    if not segments:
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Shell wrapper has no inspectable inner command.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )

    approval_decision: CommandPolicyDecision | None = None
    safe_decision: CommandPolicyDecision | None = None
    for segment in [*segments, *substitutions]:
        inspectable_segment = _strip_leading_shell_assignments(segment)
        inner = parse_command(inspectable_segment)
        if not inner.executable:
            continue
        inner_decision = _default_decision(
            outer_command,
            inner,
            request,
            policy_cwd,
            windows_command_context=windows_command_context,
        )
        if inner_decision.permission_mode == PermissionMode.blocked:
            if "outside configured rootDir" in inner_decision.reason:
                inner_decision.reason = (
                    f"Inner shell command {inner.executable} {inner_decision.reason}"
                )
            else:
                inner_decision.reason = (
                    f"Inner shell command {inner.executable} is blocked by the command policy."
                )
            return inner_decision

        configured_decision = _decision_from_configured_rules(inspectable_segment, inner, request)
        if configured_decision is not None:
            configured_decision.command = outer_command
            if configured_decision.permission_mode == PermissionMode.blocked:
                configured_decision.reason = (
                    f"Inner shell command {inner.executable} is blocked by configured "
                    f"command policy: {configured_decision.reason}"
                )
                return configured_decision
            if (
                configured_decision.permission_mode == PermissionMode.autopilot_safe
                and _configured_safe_shell_decision_can_apply(
                    inner_command,
                    script_scan_decision,
                    windows_command_context=windows_command_context,
                    powershell_command_context=powershell_command_context,
                )
            ):
                safe_decision = configured_decision
                continue
            if (
                approval_decision is None
                and configured_decision.permission_mode == PermissionMode.approval_required
            ):
                configured_decision.reason = (
                    f"Inner shell command {inner.executable} requires approval by configured "
                    f"command policy: {configured_decision.reason}"
                )
                approval_decision = configured_decision
                continue

        if (
            approval_decision is None
            and inner_decision.permission_mode == PermissionMode.approval_required
        ):
            inner_decision.reason = (
                f"Inner shell command {inner.executable} requires approval by the command policy."
            )
            approval_decision = inner_decision

    if (
        safe_decision is not None
        and not substitutions
        and not has_control_operator
        and not _shell_tokens_have_structural_or_source_approval(
            _shell_script_tokens(
                inner_command,
                windows_command_context=windows_command_context,
                powershell_command_context=powershell_command_context,
            ),
            _shell_command_position_tokens(
                _shell_script_tokens(
                    inner_command,
                    windows_command_context=windows_command_context,
                    powershell_command_context=powershell_command_context,
                )
            ),
        )
    ):
        return safe_decision

    if (
        script_scan_decision.permission_mode == PermissionMode.autopilot_safe
        and not substitutions
        and not has_control_operator
        and (approval_decision is None or approval_decision.matched_rule_id is None)
    ):
        return script_scan_decision

    if script_scan_decision.permission_mode == PermissionMode.approval_required:
        return script_scan_decision

    if approval_decision is not None:
        return approval_decision

    if substitutions:
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Shell command substitution requires approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )

    if has_control_operator:
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Compound shell commands require approval even when each segment appears safe.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )

    return CommandPolicyDecision(
        command=outer_command,
        risk=CommandRisk.safe,
        permission_mode=PermissionMode.autopilot_safe,
        reason="Command is classified as read-only or low risk.",
        agent_role=request.agent_role,
        agent_id=request.agent_id,
        task_id=request.task_id,
    )


def _configured_safe_shell_decision_can_apply(
    inner_command: str,
    script_scan_decision: CommandPolicyDecision,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> bool:
    if script_scan_decision.permission_mode == PermissionMode.autopilot_safe:
        return True
    if script_scan_decision.permission_mode != PermissionMode.approval_required:
        return False
    if script_scan_decision.reason.startswith("Launcher payload requires approval"):
        return False
    tokens = _shell_script_tokens(
        inner_command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )
    command_tokens = _shell_command_position_tokens(tokens)
    if _shell_tokens_have_structural_or_source_approval(tokens, command_tokens):
        return False
    return not any(
        _normalize_shell_executable(token) in SHELL_COMMAND_APPROVAL_TOKENS
        for token in command_tokens
    )


def _parse_inner_shell_command(parsed: ParsedCommand) -> str | None:
    flags = SHELL_COMMAND_FLAGS.get(parsed.executable)
    if flags is None:
        return None

    for index, argument in enumerate(parsed.arguments):
        normalized_argument = _strip_matching_quotes(argument.strip()).lower()
        inline_inner_command = _inline_shell_command_argument(
            parsed,
            normalized_argument,
            index,
            flags,
        )
        if inline_inner_command is not None:
            return inline_inner_command
        compact_inner_command = _compact_inner_shell_command(
            parsed,
            normalized_argument,
            index,
        )
        if compact_inner_command is not None:
            return compact_inner_command
        if _is_shell_command_flag(
            parsed.executable, normalized_argument, flags
        ) and index + 1 < len(parsed.arguments):
            if parsed.executable in {"bash", "sh"}:
                inner_command = _posix_shell_script_argument(parsed, index + 1)
            else:
                inner_command = _raw_shell_argument_tail(parsed, index + 1)
                if inner_command is None:
                    inner_command = " ".join(parsed.arguments[index + 1 :]).strip()
            inner_command = _strip_matching_quotes(inner_command.strip())
            if inner_command:
                if _inner_shell_command_needs_posix_reparse(inner_command):
                    reparsed_inner_command = _parse_inner_shell_command_with_posix(parsed, flags)
                    if reparsed_inner_command is not None:
                        return reparsed_inner_command
                return inner_command
    return None


def _inline_shell_command_argument(
    parsed: ParsedCommand,
    normalized_argument: str,
    index: int,
    flags: set[str],
) -> str | None:
    if parsed.executable in CMD_EXECUTABLES:
        return None
    inline_payload = _powershell_inline_command_payload(
        parsed.executable,
        normalized_argument,
        parsed.arguments[index],
    )
    if inline_payload is not None:
        remaining = _raw_shell_argument_tail(parsed, index + 1)
        if remaining is None:
            remaining = " ".join(parsed.arguments[index + 1 :]).strip()
        inner_command = " ".join(part for part in [inline_payload, remaining] if part).strip()
        return _strip_matching_quotes(inner_command) or None
    for flag in flags:
        for separator in (":", "="):
            prefix = f"{flag}{separator}"
            if normalized_argument.startswith(prefix):
                inline_inner = parsed.arguments[index].strip()[len(prefix) :].strip()
                remaining = _raw_shell_argument_tail(parsed, index + 1)
                if remaining is None:
                    remaining = " ".join(parsed.arguments[index + 1 :]).strip()
                inner_command = " ".join(part for part in [inline_inner, remaining] if part).strip()
                return _strip_matching_quotes(inner_command) or None
    return None


def _compact_inner_shell_command(
    parsed: ParsedCommand,
    normalized_argument: str,
    index: int,
) -> str | None:
    if parsed.executable not in CMD_EXECUTABLES:
        return None
    flag_start = _cmd_command_flag_start(normalized_argument)
    if flag_start is None:
        return None
    inline_start = flag_start + 2
    inline_inner = parsed.arguments[index].strip()[inline_start:].strip()
    if inline_inner.startswith((":", "=")):
        inline_inner = inline_inner[1:].strip()
    remaining = _raw_shell_argument_tail(parsed, index + 1)
    if remaining is None:
        remaining = " ".join(parsed.arguments[index + 1 :]).strip()
    inner_command = " ".join(part for part in [inline_inner, remaining] if part).strip()
    return _strip_matching_quotes(inner_command) or None
    return None


def _posix_shell_script_argument(parsed: ParsedCommand, argument_index: int) -> str:
    reparsed_argument = _posix_shell_reparsed_script_argument(parsed, argument_index)
    if reparsed_argument is not None:
        return reparsed_argument
    return parsed.arguments[argument_index].strip()


def _raw_shell_argument_tail(parsed: ParsedCommand, argument_index: int) -> str | None:
    if not parsed.original_command:
        return None
    target_token_index = argument_index + 1
    token_index = -1
    index = 0
    in_token = False
    quote: str | None = None
    escaped = False
    while index < len(parsed.original_command):
        char = parsed.original_command[index]
        if not in_token:
            if char.isspace():
                index += 1
                continue
            token_index += 1
            if token_index == target_token_index:
                return parsed.original_command[index:].strip()
            in_token = True
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char.isspace():
            in_token = False
        index += 1
    return None


def _is_shell_command_flag(
    executable: str,
    normalized_argument: str,
    flags: set[str],
) -> bool:
    if normalized_argument in flags:
        return True
    if executable in CMD_EXECUTABLES:
        return _cmd_command_flag_start(normalized_argument) is not None
    if executable in POWERSHELL_EXECUTABLES:
        return _is_powershell_command_flag(normalized_argument)
    if executable in {"bash", "sh"}:
        return _is_posix_clustered_command_flag(normalized_argument)
    return False


def _cmd_command_flag_start(normalized_argument: str) -> int | None:
    for index in range(len(normalized_argument) - 1):
        if normalized_argument[index] != "/":
            continue
        if normalized_argument[index + 1] in {"c", "k"}:
            return index
    return None


def _is_powershell_command_flag(normalized_argument: str) -> bool:
    if len(normalized_argument) < 2 or normalized_argument[0] not in {"-", "/"}:
        return False
    option_name = normalized_argument[1:].split(":", 1)[0].split("=", 1)[0]
    return option_name == "c" or (len(option_name) >= 3 and "command".startswith(option_name))


def _powershell_inline_command_payload(
    executable: str,
    normalized_argument: str,
    original_argument: str,
) -> str | None:
    if executable not in POWERSHELL_EXECUTABLES:
        return None
    if len(normalized_argument) < 2 or normalized_argument[0] not in {"-", "/"}:
        return None
    for separator in (":", "="):
        if separator not in normalized_argument:
            continue
        option_name, _value = normalized_argument[1:].split(separator, 1)
        if option_name == "c" or (len(option_name) >= 3 and "command".startswith(option_name)):
            return original_argument.strip().split(separator, 1)[1].strip()
    return None


def _is_posix_clustered_command_flag(normalized_argument: str) -> bool:
    if not normalized_argument.startswith("-") or normalized_argument.startswith("--"):
        return False
    return "c" in normalized_argument[1:]


def _inner_shell_command_needs_posix_reparse(inner_command: str) -> bool:
    return '\\"' in inner_command or inner_command.count('"') % 2 == 1


def _parse_inner_shell_command_with_posix(
    parsed: ParsedCommand,
    flags: set[str],
) -> str | None:
    return _posix_shell_reparsed_script_argument(parsed, 1, flags=flags)


def _posix_shell_reparsed_script_argument(
    parsed: ParsedCommand,
    fallback_argument_index: int,
    *,
    flags: set[str] | None = None,
) -> str | None:
    if not parsed.original_command:
        return None
    try:
        parts = shlex.split(parsed.original_command, posix=True)
    except ValueError:
        return None
    arguments = [_strip_matching_quotes(part) for part in parts[1:]]
    if flags is None:
        if fallback_argument_index < len(arguments):
            return arguments[fallback_argument_index]
        return None
    for index, argument in enumerate(arguments):
        if _is_shell_command_flag(
            parsed.executable, argument.strip().lower(), flags
        ) and index + 1 < len(arguments):
            inner_command = _strip_matching_quotes(arguments[index + 1].strip())
            if inner_command:
                return inner_command
    return None


def _split_shell_command_segments(
    command: str,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> tuple[list[str], bool]:
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    has_control_operator = False
    index = 0

    while index < len(command):
        char = command[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if windows_command_context and char == "^" and index + 1 < len(command):
            current.append(command[index : index + 2])
            index += 2
            continue
        if powershell_command_context and quote != "'" and char == "`":
            continuation = _escaped_line_continuation_end(command, index, "`")
            if continuation is not None:
                current.append(command[index:continuation])
                index = continuation
                continue
            if index + 1 < len(command):
                current.append(command[index : index + 2])
                index += 2
                continue
        if (
            char == "\\"
            and quote != "'"
            and not (windows_command_context or powershell_command_context)
        ):
            continuation = _escaped_line_continuation_end(command, index, "\\")
            if continuation is not None:
                current.append(command[index:continuation])
                index = continuation
                continue
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            current.append(char)
            quote = char
            index += 1
            continue
        if char in SHELL_CONTROL_OPERATORS:
            has_control_operator = True
            segment = _normalize_shell_segment("".join(current))
            if segment:
                segments.append(segment)
            current = []
            if char in {"&", "|"} and index + 1 < len(command) and command[index + 1] == char:
                index += 2
            else:
                index += 1
            continue

        current.append(char)
        index += 1

    segment = _normalize_shell_segment("".join(current))
    if segment:
        segments.append(segment)
    return segments, has_control_operator


def _normalize_shell_segment(segment: str) -> str:
    segment = segment.strip()
    while segment.startswith((". ", "& ")):
        segment = segment[1:].strip()
    if segment in {"}", ")"}:
        return ""
    while segment[:1] in {"{", "("}:
        segment = segment[1:].strip()
    while len(segment) >= 2 and (
        (segment[0] == "{" and segment[-1] == "}") or (segment[0] == "(" and segment[-1] == ")")
    ):
        segment = segment[1:-1].strip()
    return segment


def _escaped_line_continuation_end(command: str, index: int, escape_char: str) -> int | None:
    if index + 1 >= len(command) or command[index] != escape_char:
        return None
    if command[index + 1] == "\n":
        return index + 2
    if index + 2 < len(command) and command[index + 1] == "\r" and command[index + 2] == "\n":
        return index + 3
    return None


def _strip_leading_shell_assignments(segment: str) -> str:
    stripped = segment.strip()
    while True:
        updated = _LEADING_SHELL_ASSIGNMENT_RE.sub("", stripped, count=1).strip()
        if updated == stripped:
            return stripped
        stripped = updated


def _extract_shell_substitutions(
    command: str,
    *,
    powershell_command_context: bool = False,
) -> list[str]:
    substitutions: list[str] = []
    index = 0
    while index < len(command):
        if command.startswith("$(", index):
            substitution, end_index = _extract_balanced_substitution(command, index + 2)
            if substitution:
                substitutions.append(substitution)
                substitutions.extend(
                    _extract_shell_substitutions(
                        substitution,
                        powershell_command_context=powershell_command_context,
                    )
                )
            index = end_index
            continue
        if command.startswith(("<(", ">("), index):
            substitution, end_index = _extract_balanced_substitution(
                command,
                index + 2,
                extra_openers=("<(", ">("),
            )
            if substitution:
                substitutions.append(substitution)
                substitutions.extend(
                    _extract_shell_substitutions(
                        substitution,
                        powershell_command_context=powershell_command_context,
                    )
                )
            index = end_index
            continue
        if command[index] == "`" and not powershell_command_context:
            end_index = _find_backtick_substitution_end(command, index + 1)
            if end_index == -1:
                return substitutions
            substitution = command[index + 1 : end_index].strip()
            if substitution:
                substitutions.append(substitution)
                substitutions.extend(_extract_shell_substitutions(substitution.replace("\\`", "`")))
            index = end_index + 1
            continue
        index += 1
    return substitutions


def _find_backtick_substitution_end(command: str, start_index: int) -> int:
    index = start_index
    escaped = False
    nested_depth = 0
    while index < len(command):
        char = command[index]
        if escaped:
            if char == "`":
                if nested_depth == 0:
                    nested_depth += 1
                else:
                    nested_depth -= 1
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == "`":
            if nested_depth == 0:
                return index
            nested_depth -= 1
        index += 1
    return -1


def _decision_from_shell_script_tokens(
    outer_command: str,
    inner_command: str,
    request: CommandPolicyRequest,
    policy_cwd: Path,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> CommandPolicyDecision:
    tokens = _shell_script_tokens(
        inner_command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )
    command_token_indexes = _shell_command_position_token_indexes(tokens)
    command_tokens = [tokens[index] for index in command_token_indexes]
    for token in command_tokens:
        if _executable_path_targets_outside_root(
            token,
            policy_cwd,
            windows_command_context=windows_command_context,
            powershell_command_context=powershell_command_context,
        ):
            return CommandPolicyDecision(
                command=outer_command,
                risk=CommandRisk.blocked,
                permission_mode=PermissionMode.blocked,
                reason="Inner shell command executable path resolves outside configured rootDir.",
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
        blocked_command = _blocked_shell_command_name(token)
        if blocked_command is not None:
            return CommandPolicyDecision(
                command=outer_command,
                risk=CommandRisk.blocked,
                permission_mode=PermissionMode.blocked,
                reason=f"Inner shell command {blocked_command} is blocked by the command policy.",
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
    if any(
        _strip_matching_quotes(token).lower() in SHELL_BLOCK_SCAN_COMMAND_TOKENS
        for token in command_tokens
    ):
        for token in tokens:
            blocked_command = _blocked_shell_command_name(token)
            if blocked_command is not None:
                return CommandPolicyDecision(
                    command=outer_command,
                    risk=CommandRisk.blocked,
                    permission_mode=PermissionMode.blocked,
                    reason=(
                        f"Inner shell command {blocked_command} is blocked by the command policy."
                    ),
                    agent_role=request.agent_role,
                    agent_id=request.agent_id,
                    task_id=request.task_id,
                )
    nested_shell_blocked_command = _blocked_command_from_nested_shell_invocation(
        tokens,
        command_token_indexes,
    )
    if nested_shell_blocked_command is not None:
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.blocked,
            permission_mode=PermissionMode.blocked,
            reason=(
                f"Inner shell command {nested_shell_blocked_command} is blocked "
                "by the command policy."
            ),
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    for token in command_tokens:
        normalized = _normalize_shell_executable(token)
        payload_decision = _decision_from_start_process_payloads(
            outer_command,
            normalized,
            tokens,
            request,
            policy_cwd,
        )
        if payload_decision is not None:
            return payload_decision
    if _shell_tokens_have_structural_or_source_approval(tokens, command_tokens):
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Shell script constructs or redirection require approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    for token in command_tokens:
        normalized = _normalize_shell_executable(token)
        if normalized in APPROVAL_COMMANDS:
            return CommandPolicyDecision(
                command=outer_command,
                risk=CommandRisk.approval_required,
                permission_mode=PermissionMode.approval_required,
                reason=f"Inner shell command {normalized} requires approval by the command policy.",
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
        if normalized not in READ_ONLY_COMMANDS and normalized not in SHELL_COMMAND_APPROVAL_TOKENS:
            return CommandPolicyDecision(
                command=outer_command,
                risk=CommandRisk.approval_required,
                permission_mode=PermissionMode.approval_required,
                reason=(
                    f"Inner shell command {normalized} is not explicitly classified "
                    "as read-only and needs approval."
                ),
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
    if _shell_tokens_require_approval(tokens, command_tokens):
        return CommandPolicyDecision(
            command=outer_command,
            risk=CommandRisk.approval_required,
            permission_mode=PermissionMode.approval_required,
            reason="Shell script constructs or redirection require approval.",
            agent_role=request.agent_role,
            agent_id=request.agent_id,
            task_id=request.task_id,
        )
    return CommandPolicyDecision(
        command=outer_command,
        risk=CommandRisk.safe,
        permission_mode=PermissionMode.autopilot_safe,
        reason="Command is classified as read-only or low risk.",
        agent_role=request.agent_role,
        agent_id=request.agent_id,
        task_id=request.task_id,
    )


def _shell_script_tokens(
    command: str,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0

    def append_current_token() -> None:
        token = "".join(current).strip()
        if token:
            tokens.append(token)
        current.clear()

    while index < len(command):
        char = command[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if windows_command_context and char == "^" and index + 1 < len(command):
            current.append(command[index : index + 2])
            index += 2
            continue
        if char == "\\" and quote != "'":
            continuation = _escaped_line_continuation_end(command, index, "\\")
            if continuation is not None:
                current.append(command[index:continuation])
                index = continuation
                continue
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            current.append(char)
            quote = char
            index += 1
            continue
        if command.startswith("$(", index):
            _substitution, end_index = _extract_balanced_substitution(command, index + 2)
            current.append(command[index:end_index])
            index = end_index
            continue
        if powershell_command_context and quote != "'" and char == "`":
            continuation = _escaped_line_continuation_end(command, index, "`")
            if continuation is not None:
                current.append(command[index:continuation])
                index = continuation
                continue
            if index + 1 < len(command):
                current.append(command[index : index + 2])
                index += 2
                continue
            continue
        if char == "`":
            end_index = _find_backtick_substitution_end(command, index + 1)
            if end_index == -1:
                current.append(char)
                index += 1
                continue
            current.append(command[index : end_index + 1])
            index = end_index + 1
            continue
        if char.isspace():
            append_current_token()
            index += 1
            continue
        if char in {";", "&", "|", "{", "}", "(", ")", "\n"}:
            append_current_token()
            index += 1
            continue
        if char in {">", "<"}:
            append_current_token()
            if index + 1 < len(command) and command[index + 1] == char:
                tokens.append(char * 2)
                index += 2
            else:
                tokens.append(char)
                index += 1
            continue

        current.append(char)
        index += 1

    append_current_token()
    return tokens


def _shell_command_position_tokens(tokens: list[str]) -> list[str]:
    return [tokens[index] for index in _shell_command_position_token_indexes(tokens)]


def _shell_command_position_token_indexes(tokens: list[str]) -> list[int]:
    command_token_indexes: list[int] = []
    expects_command = True
    skip_next = False
    skip_command_prefix_options = False
    skip_command_prefix_option_value = False
    active_command_prefix: str | None = None
    start_title_skipped = False
    for index, token in enumerate(tokens):
        normalized = _strip_matching_quotes(token).lower()
        if (
            expects_command
            and active_command_prefix == "start-process"
            and _split_powershell_parameter_value(
                token,
                START_PROCESS_ARGUMENT_LIST_OPTIONS,
            )[0]
            is not None
            and index + 1 < len(tokens)
        ):
            payload_blocked_command = _blocked_command_from_launcher_payload(tokens[index + 1])
            if payload_blocked_command is not None:
                command_token_indexes.append(index + 1)
            skip_command_prefix_option_value = True
            continue
        if skip_next:
            skip_next = False
            expects_command = False
            skip_command_prefix_options = False
            skip_command_prefix_option_value = False
            active_command_prefix = None
            continue
        if skip_command_prefix_option_value:
            skip_command_prefix_option_value = False
            continue
        if normalized in {">", "<", "2>", ">>", "<<"}:
            skip_next = True
            continue
        if expects_command and normalized == "!":
            continue
        if expects_command and _is_shell_assignment_token(token):
            continue
        if expects_command and skip_command_prefix_options and normalized.startswith(("-", "/")):
            if _shell_prefix_option_takes_value(active_command_prefix, normalized):
                skip_command_prefix_option_value = True
            continue
        if (
            expects_command
            and active_command_prefix == "start"
            and not start_title_skipped
            and _is_quoted_token(token)
        ):
            start_title_skipped = True
            continue
        if expects_command and normalized in SHELL_COMMAND_PREFIX_TOKENS:
            command_token_indexes.append(index)
            expects_command = True
            skip_command_prefix_options = True
            active_command_prefix = normalized
            start_title_skipped = False
            continue
        if expects_command and normalized in SHELL_FLOW_COMMAND_TOKENS:
            command_token_indexes.append(index)
            expects_command = True
            skip_command_prefix_options = False
            active_command_prefix = None
            start_title_skipped = False
            continue
        if expects_command:
            command_token_indexes.append(index)
            expects_command = normalized in SHELL_COMMAND_APPROVAL_TOKENS
            skip_command_prefix_options = False
            skip_command_prefix_option_value = False
            active_command_prefix = None
            start_title_skipped = False
    return command_token_indexes


def _shell_tokens_require_approval(tokens: list[str], command_tokens: list[str]) -> bool:
    if _shell_tokens_have_structural_or_source_approval(tokens, command_tokens):
        return True
    if any(
        _strip_matching_quotes(token).lower() in SHELL_COMMAND_APPROVAL_TOKENS
        for token in command_tokens
    ):
        return True
    return False


def _shell_tokens_have_structural_or_source_approval(
    tokens: list[str],
    command_tokens: list[str],
) -> bool:
    if any(
        _strip_matching_quotes(token).lower() in SHELL_STRUCTURAL_APPROVAL_TOKENS
        for token in tokens
    ):
        return True
    return any(_strip_matching_quotes(token).lower() in {"source", "."} for token in command_tokens)


def _blocked_command_from_nested_shell_invocation(
    tokens: list[str],
    command_token_indexes: list[int],
) -> str | None:
    for command_index in command_token_indexes:
        shell_executable = _normalize_shell_executable(tokens[command_index])
        flags = SHELL_COMMAND_FLAGS.get(shell_executable)
        if flags is None:
            continue
        nested_windows_context = _host_is_windows() and shell_executable in CMD_EXECUTABLES
        nested_powershell_context = shell_executable in POWERSHELL_EXECUTABLES
        for index in range(command_index + 1, len(tokens)):
            normalized_token = _strip_matching_quotes(tokens[index]).lower()
            compact_inner_command = _compact_nested_cmd_shell_command(
                shell_executable,
                tokens,
                normalized_token,
                index,
            )
            if compact_inner_command is not None:
                compact_tokens = _shell_script_tokens(
                    compact_inner_command,
                    windows_command_context=nested_windows_context,
                    powershell_command_context=nested_powershell_context,
                )
                compact_command_indexes = _shell_command_position_token_indexes(compact_tokens)
                compact_blocked_command = _blocked_command_from_nested_shell_invocation(
                    compact_tokens,
                    compact_command_indexes,
                )
                if compact_blocked_command is not None:
                    return compact_blocked_command
                for compact_command_index in compact_command_indexes:
                    blocked_command = _blocked_shell_command_name(
                        compact_tokens[compact_command_index]
                    )
                    if blocked_command is not None:
                        return blocked_command
                break
            if not _is_shell_command_flag(shell_executable, normalized_token, flags):
                continue
            tail_tokens = tokens[index + 1 :]
            tail_command = _strip_matching_quotes(" ".join(tail_tokens).strip())
            if tail_command:
                nested_tokens = _shell_script_tokens(
                    tail_command,
                    windows_command_context=nested_windows_context,
                    powershell_command_context=nested_powershell_context,
                )
                nested_command_indexes = _shell_command_position_token_indexes(nested_tokens)
                nested_blocked_command = _blocked_command_from_nested_shell_invocation(
                    nested_tokens,
                    nested_command_indexes,
                )
                if nested_blocked_command is not None:
                    return nested_blocked_command
                for tail_command_index in nested_command_indexes:
                    blocked_command = _blocked_shell_command_name(nested_tokens[tail_command_index])
                    if blocked_command is not None:
                        return blocked_command
            break
    return None


def _compact_nested_cmd_shell_command(
    shell_executable: str,
    tokens: list[str],
    normalized_token: str,
    index: int,
) -> str | None:
    if shell_executable not in CMD_EXECUTABLES:
        return None
    flag_start = _cmd_command_flag_start(normalized_token)
    if flag_start is None:
        return None
    inline_start = flag_start + 2
    inline_inner = tokens[index].strip()[inline_start:].strip()
    if inline_inner.startswith((":", "=")):
        inline_inner = inline_inner[1:].strip()
    remaining = " ".join(tokens[index + 1 :]).strip()
    inner_command = " ".join(part for part in [inline_inner, remaining] if part).strip()
    return _strip_matching_quotes(inner_command) or None


def _blocked_command_from_start_process_argument_list(
    command_name: str,
    tokens: list[str],
) -> str | None:
    for payload in _start_process_payloads(command_name, tokens):
        blocked_command = _blocked_command_from_launcher_payload(
            payload,
        )
        if blocked_command is not None:
            return blocked_command
    return None


def _decision_from_start_process_payloads(
    outer_command: str,
    command_name: str,
    tokens: list[str],
    request: CommandPolicyRequest,
    policy_cwd: Path,
) -> CommandPolicyDecision | None:
    approval_decision: CommandPolicyDecision | None = None
    for payload in _start_process_payloads(command_name, tokens):
        blocked_command = _blocked_command_from_launcher_payload(payload)
        if blocked_command is not None:
            return CommandPolicyDecision(
                command=outer_command,
                risk=CommandRisk.blocked,
                permission_mode=PermissionMode.blocked,
                reason=f"Inner shell command {blocked_command} is blocked by the command policy.",
                agent_role=request.agent_role,
                agent_id=request.agent_id,
                task_id=request.task_id,
            )
        payload_decision = _decision_from_launcher_payload(
            outer_command,
            payload,
            request,
            policy_cwd,
        )
        if payload_decision is None:
            continue
        if payload_decision.permission_mode == PermissionMode.blocked:
            return payload_decision
        if approval_decision is None:
            approval_decision = payload_decision
    return approval_decision


def _decision_from_launcher_payload(
    outer_command: str,
    payload: str,
    request: CommandPolicyRequest,
    policy_cwd: Path,
) -> CommandPolicyDecision | None:
    payload_command = _strip_matching_quotes(payload.strip())
    if not payload_command:
        return None
    parsed_payload = parse_command(payload_command)
    payload_decision = _default_decision(
        payload_command,
        parsed_payload,
        request,
        policy_cwd,
    )
    if payload_decision.permission_mode == PermissionMode.autopilot_safe:
        return None
    reason_prefix = (
        "Launcher payload is blocked"
        if payload_decision.permission_mode == PermissionMode.blocked
        else "Launcher payload requires approval"
    )
    return CommandPolicyDecision(
        command=outer_command,
        risk=payload_decision.risk,
        permission_mode=payload_decision.permission_mode,
        reason=f"{reason_prefix}: {payload_decision.reason}",
        agent_role=request.agent_role,
        agent_id=request.agent_id,
        task_id=request.task_id,
        matched_rule_id=payload_decision.matched_rule_id,
        matched_rule_name=payload_decision.matched_rule_name,
    )


def _start_process_payloads(command_name: str, tokens: list[str]) -> list[str]:
    if command_name not in START_PROCESS_COMMAND_NAMES:
        return []
    payloads: list[str] = []
    for index, token in enumerate(tokens[:-1]):
        parameter_name, inline_value = _split_powershell_parameter_value(
            token,
            START_PROCESS_ARGUMENT_LIST_OPTIONS,
        )
        if parameter_name is None:
            continue
        payload_tokens = tokens[index + 1 :]
        if inline_value:
            payload_tokens = [inline_value, *payload_tokens]
        payload = _start_process_argument_payload(payload_tokens)
        if payload:
            payloads.append(payload)

    launcher_payload = _start_process_launcher_payload(command_name, tokens)
    if launcher_payload:
        payloads.append(launcher_payload)
    return [
        payload
        for index, payload in enumerate(payloads)
        if payload and payload not in payloads[:index]
    ]


def _split_powershell_parameter_value(
    token: str,
    parameter_names: frozenset[str],
) -> tuple[str | None, str | None]:
    cleaned = _strip_matching_quotes(token.strip())
    lowered = cleaned.lower()
    if lowered in parameter_names:
        return lowered, None
    for separator in (":", "="):
        if separator not in cleaned:
            continue
        name, value = cleaned.split(separator, 1)
        lowered_name = name.lower()
        if lowered_name in parameter_names:
            return lowered_name, value
    return None, None


def _start_process_launcher_payload(command_name: str, tokens: list[str]) -> str:
    executable: str | None = None
    argument_tokens: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        argument_name, argument_inline_value = _split_powershell_parameter_value(
            token,
            START_PROCESS_ARGUMENT_LIST_OPTIONS,
        )
        if argument_name is not None:
            argument_tokens = tokens[index + 1 :]
            if argument_inline_value:
                argument_tokens = [argument_inline_value, *argument_tokens]
            break

        file_path_name, file_path_inline_value = _split_powershell_parameter_value(
            token,
            START_PROCESS_FILE_PATH_OPTIONS,
        )
        if file_path_name is not None:
            if file_path_inline_value:
                executable = file_path_inline_value
            elif index + 1 < len(tokens):
                executable = tokens[index + 1]
                index += 1
            index += 1
            continue

        normalized = _strip_matching_quotes(token).lower()
        skips_start_option = (
            command_name == "start" and executable is None and normalized.startswith("/")
        )
        if normalized.startswith("-") or skips_start_option:
            option_name = normalized.split(":", 1)[0].split("=", 1)[0]
            if _shell_prefix_option_takes_value("start-process", option_name):
                index += 2
            else:
                index += 1
            continue

        if executable is None:
            executable = token
            index += 1
            continue

        argument_tokens = tokens[index:]
        break

    payload_parts: list[str] = []
    if executable:
        payload_parts.append(_strip_matching_quotes(executable))
    argument_payload = _start_process_argument_payload(argument_tokens)
    if argument_payload:
        payload_parts.append(argument_payload)
    return " ".join(payload_parts)


def _start_process_argument_payload(tokens: list[str]) -> str:
    payload_parts: list[str] = []
    for token in tokens:
        if token.strip().strip(",") == "@":
            continue
        normalized = _strip_matching_quotes(token).lower()
        if payload_parts and normalized.startswith("-") and "," not in token:
            break
        cleaned_parts = [
            _strip_powershell_array_syntax(_strip_matching_quotes(part.strip()))
            for part in token.strip().strip(",").split(",")
            if part.strip()
        ]
        payload_parts.extend(cleaned_parts)
        if "," not in token and len(payload_parts) == len(cleaned_parts):
            break
    return " ".join(payload_parts)


def _strip_powershell_array_syntax(token: str) -> str:
    token = token.strip()
    if token.startswith("@("):
        token = token[2:].strip()
    while token.endswith(")"):
        token = token[:-1].strip()
    return _strip_matching_quotes(token)


def _blocked_command_from_launcher_payload(payload: str) -> str | None:
    payload_command = _strip_matching_quotes(payload.strip())
    if not payload_command:
        return None
    parsed_payload = parse_command(payload_command)
    payload_inner_command = _parse_inner_shell_command(parsed_payload)
    if payload_inner_command is not None:
        blocked_inner_command = _blocked_command_from_shell_text(
            payload_inner_command,
            windows_command_context=_host_is_windows()
            and parsed_payload.executable in CMD_EXECUTABLES,
            powershell_command_context=parsed_payload.executable in POWERSHELL_EXECUTABLES,
        )
        if blocked_inner_command is not None:
            return blocked_inner_command

    payload_command = _strip_leading_shell_options(payload_command)
    blocked_shell_command = _blocked_command_from_shell_text(payload_command)
    if blocked_shell_command is not None:
        return blocked_shell_command

    tokens = _shell_script_tokens(payload_command)
    command_token_indexes = _shell_command_position_token_indexes(tokens)
    nested_blocked_command = _blocked_command_from_nested_shell_invocation(
        tokens,
        command_token_indexes,
    )
    if nested_blocked_command is not None:
        return nested_blocked_command
    for command_index in command_token_indexes:
        blocked_command = _blocked_shell_command_name(tokens[command_index])
        if blocked_command is not None:
            return blocked_command
    return None


def _blocked_command_from_shell_text(
    command: str,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> str | None:
    segments, _has_control_operator = _split_shell_command_segments(
        command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )
    substitutions = _extract_shell_substitutions(
        command,
        powershell_command_context=powershell_command_context,
    )
    for segment in [*segments, *substitutions]:
        blocked_command = _blocked_command_from_shell_segment(
            _strip_leading_shell_assignments(segment),
            windows_command_context=windows_command_context,
            powershell_command_context=powershell_command_context,
        )
        if blocked_command is not None:
            return blocked_command
    return _blocked_command_from_shell_segment(
        command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )


def _blocked_command_from_shell_segment(
    segment: str,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> str | None:
    tokens = _shell_script_tokens(
        segment,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    )
    command_token_indexes = _shell_command_position_token_indexes(tokens)
    nested_blocked_command = _blocked_command_from_nested_shell_invocation(
        tokens,
        command_token_indexes,
    )
    if nested_blocked_command is not None:
        return nested_blocked_command
    for command_index in command_token_indexes:
        blocked_command = _blocked_shell_command_name(tokens[command_index])
        if blocked_command is not None:
            return blocked_command
        payload_blocked_command = _blocked_command_from_start_process_argument_list(
            _normalize_shell_executable(tokens[command_index]),
            tokens,
        )
        if payload_blocked_command is not None:
            return payload_blocked_command
    return None


def _strip_leading_shell_options(command: str) -> str:
    tokens = _shell_script_tokens(command)
    while tokens:
        normalized = _strip_matching_quotes(tokens[0]).lower()
        if any(
            normalized == flag
            for shell_flags in SHELL_COMMAND_FLAGS.values()
            for flag in shell_flags
        ):
            tokens = tokens[1:]
            continue
        if normalized in {"-noprofile", "-noninteractive", "-executionpolicy", "-ep"}:
            tokens = (
                tokens[2:]
                if len(tokens) > 1 and normalized in {"-executionpolicy", "-ep"}
                else tokens[1:]
            )
            continue
        break
    return " ".join(tokens)


def _is_shell_assignment_token(token: str) -> bool:
    return bool(_SHELL_ASSIGNMENT_TOKEN_RE.match(token))


def _is_quoted_token(token: str) -> bool:
    stripped = token.strip()
    return (len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}) or (
        len(stripped) >= 4 and stripped[:2] == stripped[-2:] and stripped[:2] in {'\\"', "\\'"}
    )


def _normalize_shell_executable(token: str) -> str:
    variants = _shell_command_token_variants(token)
    return _normalize_executable(variants[0] if variants else token)


def _blocked_shell_command_name(token: str) -> str | None:
    for candidate in _shell_command_token_variants(token):
        normalized = _normalize_executable(candidate)
        if _blocked_command_name(normalized) is not None:
            return normalized
    return None


def _shell_command_token_variants(token: str) -> list[str]:
    stripped = _strip_matching_quotes(token.strip())
    decoded = _decode_shell_command_token(stripped)
    variants = [decoded]
    backslash_decoded = _decode_posix_backslash_escapes(decoded)
    if backslash_decoded != decoded:
        variants.append(backslash_decoded)
    if stripped != decoded:
        variants.append(stripped)
    return [
        variant
        for index, variant in enumerate(variants)
        if variant and variant not in variants[:index]
    ]


def _decode_shell_command_token(token: str) -> str:
    decoded = _ANSI_C_QUOTED_SEGMENT_RE.sub(
        lambda match: _decode_ansi_c_escapes(match.group(1)),
        token,
    )
    decoded = _LOCALIZED_QUOTED_SEGMENT_RE.sub(lambda match: match.group(1), decoded)
    decoded = _decode_cmd_caret_escapes(decoded)
    decoded = _decode_powershell_backtick_escapes(decoded)
    return decoded.replace("'", "").replace('"', "")


def _decode_ansi_c_escapes(text: str) -> str:
    escapes = {
        "a": "\a",
        "b": "\b",
        "e": "\x1b",
        "E": "\x1b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "\\": "\\",
        "'": "'",
        '"': '"',
        "?": "?",
    }
    result: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\" or index + 1 >= len(text):
            result.append(char)
            index += 1
            continue

        escaped = text[index + 1]
        if escaped == "u" and index + 5 < len(text):
            hex_digits = text[index + 2 : index + 6]
            if all(digit in "0123456789abcdefABCDEF" for digit in hex_digits):
                result.append(chr(int(hex_digits, 16)))
                index += 6
                continue
        if escaped == "U" and index + 9 < len(text):
            hex_digits = text[index + 2 : index + 10]
            if all(digit in "0123456789abcdefABCDEF" for digit in hex_digits):
                try:
                    result.append(chr(int(hex_digits, 16)))
                except ValueError:
                    result.append(f"\\U{hex_digits}")
                index += 10
                continue
        if escaped in {"x", "X"}:
            hex_digits = []
            cursor = index + 2
            while (
                cursor < len(text)
                and len(hex_digits) < 2
                and text[cursor] in "0123456789abcdefABCDEF"
            ):
                hex_digits.append(text[cursor])
                cursor += 1
            if hex_digits:
                result.append(chr(int("".join(hex_digits), 16)))
                index = cursor
                continue
        if escaped in "01234567":
            octal_digits = [escaped]
            cursor = index + 2
            while cursor < len(text) and len(octal_digits) < 3 and text[cursor] in "01234567":
                octal_digits.append(text[cursor])
                cursor += 1
            result.append(chr(int("".join(octal_digits), 8)))
            index = cursor
            continue

        result.append(escapes.get(escaped, escaped))
        index += 2
    return "".join(result)


def _decode_powershell_backtick_escapes(token: str) -> str:
    continued = re.sub(r"`\r?\n[ \t]*", "", token)
    return re.sub(r"`([\s\S])", r"\1", continued)


def _decode_posix_backslash_escapes(token: str) -> str:
    continued = re.sub(r"\\\r?\n[ \t]*", "", token)
    return re.sub(r"\\([\s\S])", r"\1", continued)


def _blocked_command_name(executable: str) -> str | None:
    if executable in BLOCKED_COMMANDS:
        return executable
    path = PureWindowsPath(executable)
    if path.suffix.lower() not in WINDOWS_EXECUTABLE_EXTENSIONS:
        return None
    stem = path.stem.lower()
    if stem in BLOCKED_COMMANDS:
        return stem
    return None


def _command_targets_protected_data_dir(
    command: str,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> bool:
    settings = get_settings()
    root_dir = settings.root_dir.resolve()
    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = root_dir / data_dir
    protected_data_dir = data_dir.resolve()
    for token in _shell_script_tokens(
        command,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    ):
        candidate_token = _strip_matching_quotes(token)
        if _token_targets_path(
            candidate_token,
            protected_data_dir,
            root_dir,
            windows_command_context=windows_command_context,
            powershell_command_context=powershell_command_context,
        ):
            return True
    return False


def _resolve_policy_cwd(cwd: Path | None) -> Path | None:
    root_dir = get_settings().root_dir.resolve()
    candidate = cwd or root_dir
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    resolved = candidate.resolve()
    if resolved != root_dir and root_dir not in resolved.parents:
        return None
    return resolved


def _host_is_windows() -> bool:
    return os.name == "nt"


def _executable_path_targets_outside_root(
    token: str,
    policy_cwd: Path,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> bool:
    for raw_candidate in _path_token_candidates(
        token,
        windows_command_context=windows_command_context,
        powershell_command_context=powershell_command_context,
    ):
        candidate = _shell_literal_executable_token_value(raw_candidate) or raw_candidate
        if not _looks_like_executable_path_token(candidate):
            continue
        if _contains_shell_variable_path(candidate):
            return True
        if candidate.startswith("~"):
            return True
        if _looks_like_windows_drive_relative_path(candidate):
            return True
        if _looks_like_windows_absolute_path(candidate):
            return _windows_path_targets_outside_root(candidate)

        normalized_candidate = candidate.replace("\\", "/")
        path = Path(normalized_candidate)
        if not path.is_absolute():
            path = policy_cwd / path
        try:
            resolved = path.resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            return True
        root_dir = get_settings().root_dir.resolve()
        if resolved != root_dir and root_dir not in resolved.parents:
            return True
    return False


def _looks_like_executable_path_token(token: str) -> bool:
    normalized = _strip_matching_quotes(token.strip())
    if not normalized:
        return False
    literal_value = _shell_literal_executable_token_value(normalized)
    if literal_value is not None:
        return _looks_like_executable_path_token(literal_value)
    if normalized.startswith(("~", "/", "./", "../", ".\\", "..\\")):
        return True
    if "/" in normalized or "\\" in normalized:
        return True
    return _looks_like_windows_drive_relative_path(normalized) or _looks_like_windows_absolute_path(
        normalized
    )


def _shell_literal_executable_token_value(token: str) -> str | None:
    stripped = token.strip()
    if not (
        _ANSI_C_QUOTED_SEGMENT_RE.fullmatch(stripped)
        or _LOCALIZED_QUOTED_SEGMENT_RE.fullmatch(stripped)
    ):
        return None
    decoded = _decode_shell_command_token(stripped)
    return decoded if decoded != stripped else None


def _read_only_command_targets_outside_root(
    parsed: ParsedCommand,
    policy_cwd: Path,
    *,
    windows_command_context: bool = False,
) -> bool:
    if parsed.executable not in READ_ONLY_PATH_COMMANDS:
        return False
    for argument in parsed.arguments:
        for candidate in _path_token_candidates(argument):
            if _path_candidate_targets_outside_root(
                candidate,
                policy_cwd,
                parsed.executable,
                windows_command_context=windows_command_context,
            ):
                return True
    return False


def _path_candidate_targets_outside_root(
    token: str,
    policy_cwd: Path,
    executable: str,
    *,
    windows_command_context: bool = False,
) -> bool:
    if not token or token in SHELL_APPROVAL_TOKENS or token in SHELL_CONTROL_OPERATORS:
        return False
    if _looks_like_command_option(
        token,
        executable,
        windows_command_context=windows_command_context,
    ):
        return False
    unescaped_token = _decode_cmd_caret_escapes(token)
    normalized_token = unescaped_token.replace("\\", "/")
    if "^" in token and any(character in unescaped_token for character in "*?["):
        return True
    if _contains_shell_variable_path(normalized_token):
        return True
    if normalized_token.startswith("~"):
        return True
    brace_expanded_candidates = _shell_brace_expansion_candidates(normalized_token)
    if brace_expanded_candidates is None:
        return True
    if brace_expanded_candidates:
        return any(
            _path_candidate_targets_outside_root(
                candidate,
                policy_cwd,
                executable,
                windows_command_context=windows_command_context,
            )
            for candidate in brace_expanded_candidates
        )
    if _glob_candidate_targets_outside_root(normalized_token, policy_cwd):
        return True
    if _looks_like_windows_drive_relative_path(unescaped_token):
        return True
    if _looks_like_windows_absolute_path(unescaped_token):
        return _windows_path_targets_outside_root(unescaped_token)
    if not _looks_like_path_token(normalized_token) and not _looks_like_bare_path_operand(token):
        return False
    settings = get_settings()
    root_dir = settings.root_dir.resolve()
    candidate = Path(normalized_token)
    if not candidate.is_absolute():
        candidate = policy_cwd / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return True
    return resolved != root_dir and root_dir not in resolved.parents


def _looks_like_command_option(
    token: str,
    executable: str,
    *,
    windows_command_context: bool = False,
) -> bool:
    if token.startswith("-") and not token.startswith(("./", "../", "/")):
        return True
    return windows_command_context and _looks_like_windows_slash_option(token, executable)


def _looks_like_windows_slash_option(token: str, executable: str) -> bool:
    normalized = token.lower()
    if executable == "type":
        return normalized == "/?"
    if executable != "dir":
        return False
    if normalized in {
        "/?",
        "/4",
        "/b",
        "/c",
        "/-c",
        "/d",
        "/l",
        "/n",
        "/p",
        "/q",
        "/r",
        "/s",
        "/w",
        "/x",
    }:
        return True
    return bool(
        re.fullmatch(r"/a(?::?-?[drhasilo]+)?", normalized)
        or re.fullmatch(r"/o(?::?-?[nsedg]+)?", normalized)
        or re.fullmatch(r"/t(?::?[caw])?", normalized)
    )


def _decode_cmd_caret_escapes(token: str) -> str:
    return re.sub(r"\^(.)", r"\1", token)


def _shell_brace_expansion_candidates(token: str) -> list[str] | None:
    start = token.find("{")
    if start == -1:
        return []
    end = token.find("}", start + 1)
    if end == -1:
        return None
    payload = token[start + 1 : end]
    if not payload or "{" in payload or "}" in payload:
        return None
    if "," not in payload:
        return None if ".." in payload else []
    prefix = token[:start]
    suffix = token[end + 1 :]
    return [f"{prefix}{alternative}{suffix}" for alternative in payload.split(",")]


def _glob_candidate_targets_outside_root(token: str, policy_cwd: Path) -> bool:
    if not any(character in token for character in "*?["):
        return False
    candidate = Path(token)
    if not candidate.is_absolute():
        candidate = policy_cwd / candidate
    root_dir = get_settings().root_dir.resolve()
    for match in glob.glob(str(candidate), recursive=False):
        try:
            resolved = Path(match).resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            return True
        if resolved != root_dir and root_dir not in resolved.parents:
            return True
    return False


def _looks_like_windows_drive_relative_path(token: str) -> bool:
    path = PureWindowsPath(token)
    return bool(path.drive and not path.root)


def _looks_like_windows_absolute_path(token: str) -> bool:
    path = PureWindowsPath(token)
    return bool(path.drive and path.root)


def _windows_path_targets_outside_root(token: str) -> bool:
    root_path = _collapse_windows_path(str(get_settings().root_dir.resolve()))
    token_path = _collapse_windows_path(token)
    if not root_path.drive:
        return True
    token_normalized = str(token_path).lower()
    root_normalized = str(root_path).lower().rstrip("\\")
    return token_normalized != root_normalized and not token_normalized.startswith(
        root_normalized + "\\"
    )


def _collapse_windows_path(token: str) -> PureWindowsPath:
    path = PureWindowsPath(token)
    collapsed_parts: list[str] = []
    for part in path.parts:
        if part in {path.drive, path.root, path.anchor, "\\"}:
            continue
        if part == ".":
            continue
        if part == "..":
            if collapsed_parts:
                collapsed_parts.pop()
            else:
                collapsed_parts.append(part)
            continue
        collapsed_parts.append(part)
    return PureWindowsPath(path.anchor, *collapsed_parts)


def _contains_shell_variable_path(token: str) -> bool:
    return bool(_SHELL_PATH_EXPANSION_RE.search(token) or _WINDOWS_PATH_EXPANSION_RE.search(token))


def _looks_like_path_token(token: str) -> bool:
    return token.startswith(("/", "./", "../", "~/")) or "/" in token or token in {".", ".."}


def _looks_like_bare_path_operand(token: str) -> bool:
    return bool(token)


def _token_targets_path(
    token: str,
    protected_data_dir: PureWindowsPath,
    root_dir: PureWindowsPath,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> bool:
    return any(
        _path_candidate_targets_path(candidate, protected_data_dir, root_dir)
        for candidate in _path_token_candidates(
            token,
            windows_command_context=windows_command_context,
            powershell_command_context=powershell_command_context,
        )
    )


def _path_token_candidates(
    token: str,
    *,
    windows_command_context: bool = False,
    powershell_command_context: bool = False,
) -> list[str]:
    stripped = _strip_matching_quotes(token.strip())
    if _contains_shell_variable_path(stripped):
        return [stripped]
    decoded_variants = [stripped]
    if windows_command_context:
        decoded_variants.append(_decode_cmd_caret_escapes(stripped))
    if powershell_command_context:
        decoded_variants.append(_decode_powershell_backtick_escapes(stripped))
    if not windows_command_context and not powershell_command_context:
        decoded_variants.append(_decode_posix_backslash_escapes(stripped))

    candidates: list[str] = []
    for variant in decoded_variants:
        cleaned = variant.replace('"', "").replace("'", "")
        if not cleaned:
            continue
        candidates.append(cleaned)
        if cleaned.startswith("-"):
            for separator in (":", "="):
                if separator in cleaned:
                    _name, value = cleaned.split(separator, 1)
                    if value:
                        candidates.append(value)
                    break
    return [
        candidate
        for index, candidate in enumerate(candidates)
        if candidate and candidate not in candidates[:index]
    ]


def _path_candidate_targets_path(
    token: str,
    protected_data_dir: PureWindowsPath,
    root_dir: PureWindowsPath,
) -> bool:
    if not token or token in SHELL_APPROVAL_TOKENS or token in SHELL_CONTROL_OPERATORS:
        return False
    normalized_token = token.replace("/", "\\")
    lowered_token = normalized_token.lower()
    if _path_candidate_matches_protected_dir_name(lowered_token, protected_data_dir):
        return True
    if (
        ".dgentic" in lowered_token
        or "\\state" in lowered_token
        or lowered_token.startswith("state\\")
    ):
        return True
    try:
        token_path = PureWindowsPath(normalized_token)
        if not token_path.is_absolute():
            token_path = PureWindowsPath(root_dir) / token_path
        normalized_path = str(token_path).lower()
        protected_path = str(protected_data_dir).lower()
        return normalized_path == protected_path or normalized_path.startswith(
            protected_path.rstrip("\\") + "\\"
        )
    except ValueError:
        return False


def _path_candidate_matches_protected_dir_name(
    lowered_token: str,
    protected_data_dir: PureWindowsPath,
) -> bool:
    protected_names = {".dgentic", protected_data_dir.name.lower()}
    for segment in re.split(r"\\+", lowered_token):
        segment = segment.strip()
        if not segment:
            continue
        if any(fnmatchcase(name, segment) for name in protected_names):
            return True
    return False


def _shell_prefix_option_takes_value(prefix: str | None, option: str) -> bool:
    if prefix is None:
        return False
    if "=" in option:
        return False
    options_with_values = SHELL_COMMAND_PREFIX_OPTIONS_WITH_VALUES.get(prefix, frozenset())
    return option in options_with_values


def _extract_balanced_substitution(
    command: str,
    start_index: int,
    *,
    extra_openers: tuple[str, ...] = (),
) -> tuple[str, int]:
    depth = 1
    quote: str | None = None
    escaped = False
    current: list[str] = []
    index = start_index

    while index < len(command):
        char = command[index]
        if escaped:
            current.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            index += 1
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            current.append(char)
            quote = char
            index += 1
            continue
        if command.startswith("$(", index) or any(
            command.startswith(opener, index) for opener in extra_openers
        ):
            depth += 1
            current.append(command[index : index + 2])
            index += 2
            continue
        if char == ")":
            depth -= 1
            if depth == 0:
                return "".join(current).strip(), index + 1
            current.append(char)
            index += 1
            continue
        current.append(char)
        index += 1

    return "", len(command)


def _risk_for_permission(permission_mode: PermissionMode) -> CommandRisk:
    if permission_mode == PermissionMode.blocked:
        return CommandRisk.blocked
    if permission_mode == PermissionMode.approval_required:
        return CommandRisk.approval_required
    return CommandRisk.safe


def _normalize_agent_roles(agent_roles: list[str]) -> list[str]:
    return sorted({role.strip().lower() for role in agent_roles if role.strip()})


def _record_decision(decision: CommandPolicyDecision, *, actor: str | None = None) -> None:
    metadata = decision.model_dump(mode="json")
    metadata["command"] = _redact_sensitive_values(metadata["command"])
    event_log.record(
        LogEventType.cli,
        "Evaluated CLI command policy.",
        actor=actor or "system",
        metadata=metadata,
    )


def _redact_sensitive_values(text: str) -> str:
    return _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('key')}=[REDACTED]",
        _SENSITIVE_FLAG_RE.sub(
            lambda match: f"{match.group('prefix')}[REDACTED]",
            _redact_substitution_secret_values(text),
        ),
    )


def _redact_substitution_secret_values(text: str) -> str:
    result = text
    for match in list(_SENSITIVE_ASSIGNMENT_PREFIX_RE.finditer(result))[::-1]:
        result = _redact_balanced_substitution_value(result, match.end(), "")
    for match in list(_SENSITIVE_FLAG_PREFIX_RE.finditer(result))[::-1]:
        result = _redact_balanced_substitution_value(result, match.end(), match.group("prefix"))
    return result


def _redact_balanced_substitution_value(text: str, value_start: int, prefix: str) -> str:
    if not text.startswith("$(", value_start):
        return text
    end_index = _find_balanced_substitution_end(text, value_start + 2)
    if end_index == -1:
        return text
    redacted = f"{prefix}[REDACTED]"
    return text[: value_start - len(prefix)] + redacted + text[end_index:]


def _find_balanced_substitution_end(text: str, start_index: int) -> int:
    depth = 1
    quote: str | None = None
    escaped = False
    index = start_index
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if text.startswith("$(", index):
            depth += 1
            index += 2
            continue
        if char == ")":
            depth -= 1
            index += 1
            if depth == 0:
                return index
            continue
        index += 1
    return -1
