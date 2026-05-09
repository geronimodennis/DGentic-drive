import pytest

from dgentic.command_policy import (
    create_command_policy_rule,
    evaluate_command_policy,
    list_command_policy_rules,
    parse_command,
    update_command_policy_rule,
)
from dgentic.events import event_log
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandPolicyMatchType,
    CommandPolicyRequest,
    CommandPolicyRuleRequest,
    CommandPolicyRuleUpdate,
    LogEventType,
    PermissionMode,
)
from dgentic.settings import get_settings


@pytest.fixture
def policy_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    data_dir = tmp_path / "state"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    get_settings.cache_clear()

    yield root_dir, data_dir

    get_settings.cache_clear()


def test_command_policy_rules_override_defaults_and_match_arguments(policy_state) -> None:
    _root_dir, data_dir = policy_state

    default_decision = evaluate_command_policy(CommandPolicyRequest(command="git status"))

    assert default_decision.permission_mode == PermissionMode.approval_required

    allow_git = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow git status checks",
            match_type=CommandPolicyMatchType.executable,
            pattern="git",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Read-only git inspection is allowed in this workspace.",
            priority=20,
        )
    )
    block_dangerous_arg = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Block dangerous argument",
            match_type=CommandPolicyMatchType.argument_contains,
            pattern="--dangerous",
            permission_mode=PermissionMode.blocked,
            reason="Dangerous CLI arguments are denied before execution.",
            priority=10,
        )
    )

    safe_decision = evaluate_command_policy(CommandPolicyRequest(command="git status"))
    blocked_decision = evaluate_command_policy(
        CommandPolicyRequest(command="git status --dangerous")
    )

    assert safe_decision.permission_mode == PermissionMode.autopilot_safe
    assert safe_decision.matched_rule_id == allow_git.id
    assert blocked_decision.permission_mode == PermissionMode.blocked
    assert blocked_decision.matched_rule_id == block_dangerous_arg.id
    assert [rule.id for rule in list_command_policy_rules()] == [
        block_dangerous_arg.id,
        allow_git.id,
    ]
    assert (data_dir / "cli-command-policy-rules.json").exists()


def test_command_policy_rules_can_be_disabled(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Block temporary marker",
            match_type=CommandPolicyMatchType.contains,
            pattern="temporary-marker",
            permission_mode=PermissionMode.blocked,
            reason="Temporary marker is blocked while enabled.",
        )
    )

    blocked = evaluate_command_policy(CommandPolicyRequest(command="cmd /c echo temporary-marker"))
    disabled = update_command_policy_rule(rule.id, CommandPolicyRuleUpdate(enabled=False))
    allowed = evaluate_command_policy(CommandPolicyRequest(command="cmd /c echo temporary-marker"))

    assert blocked.permission_mode == PermissionMode.blocked
    assert disabled is not None
    assert disabled.enabled is False
    assert allowed.permission_mode == PermissionMode.autopilot_safe


def test_command_policy_rules_can_be_scoped_to_agent_roles(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Developers may inspect git",
            match_type=CommandPolicyMatchType.executable,
            pattern="git",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Developer git inspection is allowed.",
            agent_roles=["Developer"],
        )
    )

    developer_decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="git status",
            agent_role="developer",
            agent_id="agent-dev-1",
            task_id="story-5.3",
        )
    )
    qa_decision = evaluate_command_policy(
        CommandPolicyRequest(command="git status", agent_role="qa")
    )

    assert rule.agent_roles == ["developer"]
    assert developer_decision.permission_mode == PermissionMode.autopilot_safe
    assert developer_decision.matched_rule_id == rule.id
    assert developer_decision.agent_id == "agent-dev-1"
    assert developer_decision.task_id == "story-5.3"
    assert qa_decision.permission_mode == PermissionMode.approval_required


def test_shell_wrapped_blocked_commands_do_not_bypass_policy(policy_state) -> None:
    _root_dir, _data_dir = policy_state

    blocked = evaluate_command_policy(CommandPolicyRequest(command="cmd /c del important.txt"))
    safe_shell_read = evaluate_command_policy(CommandPolicyRequest(command="cmd /c echo hello"))

    assert blocked.permission_mode == PermissionMode.blocked
    assert "Inner shell command del is blocked" in blocked.reason
    assert safe_shell_read.permission_mode == PermissionMode.autopilot_safe


@pytest.mark.parametrize(
    ("command", "expected_mode", "reason_fragment"),
    [
        ("cmd /c del important.txt", PermissionMode.blocked, "Inner shell command del is blocked"),
        (
            "cmd /c shutdown.exe /s",
            PermissionMode.blocked,
            "Inner shell command shutdown.exe is blocked",
        ),
        (
            "cmd /cdel important.txt",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "cmd /cshutdown.exe /s",
            PermissionMode.blocked,
            "Inner shell command shutdown.exe is blocked",
        ),
        (
            "cmd /c format.com C:",
            PermissionMode.blocked,
            "Inner shell command format.com is blocked",
        ),
        (
            "cmd /c rd /s /q important",
            PermissionMode.blocked,
            "Inner shell command rd is blocked",
        ),
        (
            "cmd /c erase important.txt",
            PermissionMode.blocked,
            "Inner shell command erase is blocked",
        ),
        (
            "cmd.exe /c git status",
            PermissionMode.approval_required,
            "Inner shell command git requires approval",
        ),
        ("powershell -Command echo hello", PermissionMode.autopilot_safe, "low risk"),
        ("powershell -c echo hello", PermissionMode.autopilot_safe, "low risk"),
        (
            "powershell.exe -Command python --version",
            PermissionMode.approval_required,
            "Inner shell command python requires approval",
        ),
        (
            "pwsh -Command rm -rf important",
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            "powershell -Command ri important.txt",
            PermissionMode.blocked,
            "Inner shell command ri is blocked",
        ),
        (
            "powershell -Command rd important",
            PermissionMode.blocked,
            "Inner shell command rd is blocked",
        ),
        (
            "powershell -Command erase important.txt",
            PermissionMode.blocked,
            "Inner shell command erase is blocked",
        ),
        ("pwsh -c echo hello", PermissionMode.autopilot_safe, "low risk"),
        ("sh -c rm -rf important", PermissionMode.blocked, "Inner shell command rm is blocked"),
        ("sh -ec rm -rf important", PermissionMode.blocked, "Inner shell command rm is blocked"),
        (
            "sh -c rm.exe -rf important",
            PermissionMode.blocked,
            "Inner shell command rm.exe is blocked",
        ),
        (
            "bash -c git status",
            PermissionMode.approval_required,
            "Inner shell command git requires approval",
        ),
        (
            "bash -lc rm -rf important",
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        ("cmd /k del important.txt", PermissionMode.blocked, "Inner shell command del is blocked"),
        (
            "cmd /kdel important.txt",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        ("bash -c echo hello", PermissionMode.autopilot_safe, "low risk"),
    ],
)
def test_shell_wrapper_matrix_classifies_inner_command_risk(
    policy_state,
    command: str,
    expected_mode: PermissionMode,
    reason_fragment: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == expected_mode
    assert reason_fragment in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "shutdown.exe /s",
        "format.com C:",
        "rm.exe -rf important",
        "rd /s /q important",
        "erase important.txt",
        "ri important.txt",
    ],
)
def test_windows_executable_extensions_do_not_bypass_blocked_commands(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked


@pytest.mark.parametrize(
    "command",
    [
        'cmd /c "start /b del important.txt"',
        'cmd /c "start /wait rm.exe -rf important"',
        'cmd /c "start \\"title\\" del important.txt"',
        'cmd /c "start \\"\\" rm.exe -rf important"',
        "cmd /c \"start /b bash -c 'rm -rf important'\"",
        "cmd /c \"start /b powershell -Command 'Remove-Item important.txt'\"",
        'cmd /c "start /b cmd /cdel important.txt"',
        'cmd /c "start /b cmd.exe /cdel important.txt"',
    ],
)
def test_cmd_start_does_not_skip_blocked_launched_commands(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked


def test_configured_safe_rules_do_not_downgrade_shell_redirection(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow echo text",
            match_type=CommandPolicyMatchType.contains,
            pattern="echo owned",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Echo text is allowed.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "echo owned > file"'))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "redirection require approval" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "cmd /c mkdir created",
        "cmd /c copy /Y source.txt target.txt",
        "touch file",
        "mv source.txt target.txt",
        "cp source.txt target.txt",
    ],
)
def test_unknown_or_mutating_commands_require_approval(policy_state, command: str) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required


@pytest.mark.parametrize(
    "command",
    [
        "cat .dgentic/cli-approval-digest.key",
        "cat .dgen*/cli-approval-digest.key",
        "dir .dgentic",
        "cmd /c type .dgentic\\cli-approval-digest.key",
        "cmd /c type .dgenti?\\cli-approval-digest.key",
        'powershell -Command "type -Path:.dgentic\\cli-approval-digest.key"',
        'powershell -Command "type .dgenti?/cli-approval-digest.key"',
        "bash -c 'cat .dgen\"tic\"/cli-approval-digest.key'",
        'bash -c "cat .dgen*/cli-approval-digest.key"',
    ],
)
def test_cli_read_commands_targeting_state_require_approval(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "DGentic state files" in decision.reason


def test_cli_read_commands_targeting_posix_absolute_state_paths_require_approval(
    policy_state,
) -> None:
    _root_dir, data_dir = policy_state
    posix_state_path = "/" + data_dir.as_posix().split(":", 1)[-1].lstrip("/")

    decision = evaluate_command_policy(
        CommandPolicyRequest(command=f"cat {posix_state_path}/cli-approval-digest.key")
    )

    assert decision.permission_mode == PermissionMode.approval_required
    assert "DGentic state files" in decision.reason


@pytest.mark.parametrize(
    ("executable", "command"),
    [
        ("cat", "cat .dgentic/cli-approval-digest.key"),
        ("cat", "cat .dgen*/cli-approval-digest.key"),
        ("dir", "dir .dgentic"),
        ("type", "type .dgentic/cli-approval-digest.key"),
        ("powershell", 'powershell -Command "type -Path:.dgentic\\cli-approval-digest.key"'),
    ],
)
def test_configured_safe_rules_do_not_downgrade_state_file_reads(
    policy_state,
    executable: str,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name=f"Allow {executable}",
            match_type=CommandPolicyMatchType.executable,
            pattern=executable,
            permission_mode=PermissionMode.autopilot_safe,
            reason=f"{executable} is usually read-only.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "DGentic state files" in decision.reason


@pytest.mark.parametrize(
    ("command", "expected_mode", "reason_fragment"),
    [
        (
            'cmd /c "echo ok & del important.txt"',
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'bash -c "echo ok; rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'pwsh -Command "& { Remove-Item important.txt }"',
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            'sh -c "echo ok; echo next"',
            PermissionMode.approval_required,
            "Compound shell commands require approval",
        ),
    ],
)
def test_compound_shell_wrappers_inspect_each_segment(
    policy_state,
    command: str,
    expected_mode: PermissionMode,
    reason_fragment: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == expected_mode
    assert reason_fragment in decision.reason


@pytest.mark.parametrize(
    ("command", "expected_mode", "reason_fragment"),
    [
        (
            'bash -c "echo $(rm -rf important)"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'sh -c "echo `rm -rf important`"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'pwsh -Command "Write-Output $(Remove-Item important.txt)"',
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            'bash -c "echo $(echo nested)"',
            PermissionMode.approval_required,
            "Shell command substitution requires approval",
        ),
        (
            'bash -c "echo $(echo $(rm -rf important))"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "cat <(rm -rf important)"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "cat >(rm -rf important)"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "cat <(echo <(rm -rf important))"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
    ],
)
def test_shell_command_substitutions_are_not_classified_safe(
    policy_state,
    command: str,
    expected_mode: PermissionMode,
    reason_fragment: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == expected_mode
    assert reason_fragment in decision.reason


def test_configured_rules_apply_to_inner_shell_segments(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Block custom deploy tool",
            match_type=CommandPolicyMatchType.executable,
            pattern="deploy-tool",
            permission_mode=PermissionMode.blocked,
            reason="Deploy tool is blocked in this context.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(
        CommandPolicyRequest(command='bash -c "echo ok; deploy-tool prod"')
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert decision.matched_rule_id == rule.id
    assert "configured command policy" in decision.reason


def test_configured_safe_rules_apply_to_inner_shell_segments(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow git status in shell wrapper",
            match_type=CommandPolicyMatchType.exact,
            pattern="git status",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Git status is allowed for this role.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "git status"'))

    assert decision.permission_mode == PermissionMode.autopilot_safe
    assert decision.matched_rule_id == rule.id
    assert rule.enabled is True


def test_configured_safe_rules_do_not_preempt_shell_wrapper_inspection(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Broad allow git status",
            match_type=CommandPolicyMatchType.contains,
            pattern="git status",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Git status is allowed.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(
        CommandPolicyRequest(command='bash -c "git status; rm -rf important"')
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert "Inner shell command rm is blocked" in decision.reason


def test_configured_approval_rules_do_not_preempt_shell_wrapper_blocking(
    policy_state,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Review git status wrapper",
            match_type=CommandPolicyMatchType.contains,
            pattern="git status",
            permission_mode=PermissionMode.approval_required,
            reason="Git status wrappers require approval.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(
        CommandPolicyRequest(command='bash -c "git status; rm -rf important"')
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert "Inner shell command rm is blocked" in decision.reason


def test_configured_blocked_rules_can_target_safe_shell_wrappers(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    rule = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Block bash wrappers",
            match_type=CommandPolicyMatchType.executable,
            pattern="bash",
            permission_mode=PermissionMode.blocked,
            reason="Bash wrappers are disabled in this context.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "echo hello"'))

    assert decision.permission_mode == PermissionMode.blocked
    assert decision.matched_rule_id == rule.id
    assert decision.reason == "Bash wrappers are disabled in this context."


@pytest.mark.parametrize(
    "permission_mode", [PermissionMode.autopilot_safe, PermissionMode.approval_required]
)
def test_configured_rules_matching_blocked_inner_commands_cannot_downgrade_builtin_blocks(
    policy_state,
    permission_mode: PermissionMode,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name=f"Configured {permission_mode} for rm",
            match_type=CommandPolicyMatchType.executable,
            pattern="rm",
            permission_mode=permission_mode,
            reason="Configured rule must not override built-in blocked commands.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "rm -rf important"'))

    assert decision.permission_mode == PermissionMode.blocked
    assert "Inner shell command rm is blocked" in decision.reason


@pytest.mark.parametrize(
    "permission_mode", [PermissionMode.autopilot_safe, PermissionMode.approval_required]
)
def test_configured_rules_cannot_downgrade_direct_builtin_blocks(
    policy_state,
    permission_mode: PermissionMode,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name=f"Configured {permission_mode} for direct rm",
            match_type=CommandPolicyMatchType.executable,
            pattern="rm",
            permission_mode=permission_mode,
            reason="Configured rule must not override direct built-in blocked commands.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command="rm -rf important"))

    assert decision.permission_mode == PermissionMode.blocked
    assert "rm is blocked" in decision.reason


def test_escaped_nested_backtick_substitutions_block_inner_commands(policy_state) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(
        CommandPolicyRequest(command='bash -c "echo `echo \\`rm -rf important\\``"')
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert "Inner shell command rm is blocked" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'bash -c "{ rm -rf important; }"',
        'bash -c "( rm -rf important; )"',
        'pwsh -Command "{ Remove-Item important.txt; }"',
    ],
)
def test_grouped_shell_blocks_with_separators_expose_blocked_commands(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked


@pytest.mark.parametrize(
    "command",
    [
        'pwsh -Command ". { Remove-Item important.txt }"',
        'pwsh -Command ". { Remove-Item important.txt; }"',
        'pwsh -Command "if ($true) { Remove-Item important.txt }"',
        'cmd /c "if exist important.txt del important.txt"',
    ],
)
def test_shell_script_keywords_and_dot_sourced_blocks_expose_blocked_commands(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked


@pytest.mark.parametrize(
    "command",
    [
        'bash -c "echo owned > file"',
        'bash -c "echo owned>file"',
        'bash -c "cat < input.txt"',
        'sh -c "cat<input.txt"',
        'cmd /c "echo owned > file"',
        'cmd /c "echo owned>file"',
        'bash -c "echo err 2>file"',
    ],
)
def test_shell_redirection_requires_approval(policy_state, command: str) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "redirection require approval" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'bash -c ". ./script.sh"',
        'bash -c "source ./script.sh"',
    ],
)
def test_shell_source_execution_requires_approval(policy_state, command: str) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "redirection require approval" in decision.reason


@pytest.mark.parametrize(
    ("command", "expected_mode", "reason_fragment"),
    [
        (
            'bash -c "command rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "exec rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "time rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "! rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "VAR=x rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            "bash -c \"VAR='x y' rm -rf important\"",
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            "bash -c 'VAR=\"x y\" rm -rf important'",
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "VAR=$(echo x) rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "env -i VAR=x rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            "bash -c \"env VAR='x y' rm -rf important\"",
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'bash -c "sudo -u root rm -rf important"',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            'cmd /c "call del important.txt"',
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'cmd /c "start /b powershell -Command Remove-Item important.txt"',
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            'powershell -Command "Start-Process powershell -ArgumentList '
            "'-Command Remove-Item important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            'powershell -Command "Start-Process powershell -ArgumentList '
            "'-NoProfile','-Command','Remove-Item important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -Command \"Start-Process cmd -ArgumentList '/c','del important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process cmd -ArgumentList:/c,del important.txt"',
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process cmd -ArgumentList=/c,del important.txt"',
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process cmd -Args:/c,del important.txt"',
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process powershell -ArgumentList '
            "@('-Command','Remove-Item important.txt')\"",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -Command \"Start-Process cmd '/c del important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "powershell -Command \"Start-Process -FilePath cmd '/c del important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "powershell -Command \"saps cmd '/c del important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "powershell -Command \"start cmd '/c del important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process -FilePath powershell '
            "-ArgumentList '-Command Remove-Item important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            'powershell -Command "Start-Process powershell -Args '
            "'-Command Remove-Item important.txt'\"",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            'bash -c "builtin source ./script.sh"',
            PermissionMode.approval_required,
            "redirection require approval",
        ),
        (
            'bash -c "command . ./script.sh"',
            PermissionMode.approval_required,
            "redirection require approval",
        ),
    ],
)
def test_shell_command_prefixes_inspect_wrapped_commands(
    policy_state,
    command: str,
    expected_mode: PermissionMode,
    reason_fragment: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == expected_mode
    assert reason_fragment in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "powershell -Command \"Start-Process cmd '/c del important.txt'\"",
        'powershell -Command "Start-Process cmd -ArgumentList:/c,del important.txt"',
        "powershell -Command \"Start-Process -FilePath cmd '/c del important.txt'\"",
    ],
)
def test_configured_safe_rules_do_not_downgrade_start_process_payload_blocks(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow Start-Process text",
            match_type=CommandPolicyMatchType.contains,
            pattern="Start-Process",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Start-Process is allowed by configured policy.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert "Inner shell command del is blocked" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'bash -c "echo rm"',
        'bash -c "echo command rm"',
        'bash -c "echo if rm"',
        "bash -c \"VAR='x y' echo rm\"",
        'cmd /c "echo call del"',
        "pwsh -Command \"Write-Output 'Remove-Item'\"",
    ],
)
def test_shell_script_scan_does_not_block_data_tokens(policy_state, command: str) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.autopilot_safe


def test_shell_redirection_does_not_block_data_tokens(policy_state) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "echo rm > file"'))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "redirection require approval" in decision.reason


def test_command_policy_event_metadata_redacts_substitution_secret_values(policy_state) -> None:
    _root_dir, _data_dir = policy_state

    evaluate_command_policy(
        CommandPolicyRequest(
            command=(
                "python deploy.py --token=$(printf SUPER_SECRET; echo ok) "
                "SECRET=$(printf ASSIGNMENT_SECRET; echo ok)"
            )
        )
    )

    latest_event = event_log.list(LogEventType.cli)[-1]
    redacted_command = latest_event.metadata["command"]
    assert "--token=[REDACTED]" in redacted_command
    assert "SECRET=[REDACTED]" in redacted_command
    assert "SUPER_SECRET" not in redacted_command
    assert "ASSIGNMENT_SECRET" not in redacted_command
    assert "echo ok)" not in redacted_command


@pytest.mark.parametrize(
    "command",
    [
        "cmd /c",
        "cmd.exe /c",
        "powershell -Command",
        "powershell -c",
        "powershell.exe -Command",
        "pwsh -Command",
        "pwsh -c",
        "sh -c",
        "bash -c",
    ],
)
def test_uninspectable_shell_wrappers_require_approval(policy_state, command: str) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "no inspectable inner command" in decision.reason


@pytest.mark.parametrize(
    ("command", "expected_executable", "expected_arguments"),
    [
        (
            '"C:\\Program Files\\Git\\bin\\git.exe" "status check"',
            "git.exe",
            ["status check"],
        ),
        ("'/usr/local/bin/git' 'status check'", "git", ["status check"]),
        ("bash -c \"echo 'hello world'\"", "bash", ["-c", "echo 'hello world'"]),
        ("pwsh -c 'echo \"hello world\"'", "pwsh", ["-c", 'echo "hello world"']),
        ('cmd /c "echo hello world"', "cmd", ["/c", "echo hello world"]),
    ],
)
def test_parser_preserves_quoted_arguments_and_normalizes_executable_paths(
    command: str,
    expected_executable: str,
    expected_arguments: list[str],
) -> None:
    parsed = parse_command(command)

    assert parsed.executable == expected_executable
    assert parsed.arguments == expected_arguments


def test_policy_rules_stay_stable_across_match_types_priority_and_scope(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    disabled = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Disabled broad contains rule",
            match_type=CommandPolicyMatchType.contains,
            pattern="needle",
            permission_mode=PermissionMode.blocked,
            reason="Disabled rules must not participate in matching.",
            enabled=False,
            priority=0,
        )
    )
    high_priority_argument = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Argument marker wins",
            match_type=CommandPolicyMatchType.argument_contains,
            pattern="needle flag",
            permission_mode=PermissionMode.blocked,
            reason="Argument markers are blocked before lower-priority matches.",
            priority=1,
        )
    )
    executable = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Quoted git executable is safe for QA",
            match_type=CommandPolicyMatchType.executable,
            pattern="C:\\Program Files\\Git\\bin\\git.exe",
            permission_mode=PermissionMode.autopilot_safe,
            reason="QA may inspect quoted git executable paths.",
            agent_roles=["QA"],
            priority=10,
        )
    )
    exact = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Exact command fallback",
            match_type=CommandPolicyMatchType.exact,
            pattern='git status "needle flag"',
            permission_mode=PermissionMode.approval_required,
            reason="Exact matches still work after argument matching.",
            priority=20,
        )
    )
    contains = create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Contains fallback",
            match_type=CommandPolicyMatchType.contains,
            pattern="ordinary-marker",
            permission_mode=PermissionMode.approval_required,
            reason="Contains rules match normalized command text.",
            priority=30,
        )
    )

    argument_decision = evaluate_command_policy(
        CommandPolicyRequest(command='git status "needle flag"', agent_role="qa")
    )
    executable_decision = evaluate_command_policy(
        CommandPolicyRequest(
            command='"C:\\Program Files\\Git\\bin\\git.exe" status',
            agent_role="qa",
        )
    )
    scoped_out_decision = evaluate_command_policy(
        CommandPolicyRequest(
            command='"C:\\Program Files\\Git\\bin\\git.exe" status',
            agent_role="developer",
        )
    )
    exact_decision = evaluate_command_policy(
        CommandPolicyRequest(command='git status "needle flag"')
    )
    contains_decision = evaluate_command_policy(
        CommandPolicyRequest(command="echo ordinary-marker")
    )

    assert disabled.enabled is False
    assert argument_decision.permission_mode == PermissionMode.blocked
    assert argument_decision.matched_rule_id == high_priority_argument.id
    assert executable_decision.permission_mode == PermissionMode.autopilot_safe
    assert executable_decision.matched_rule_id == executable.id
    assert scoped_out_decision.permission_mode == PermissionMode.approval_required
    assert scoped_out_decision.matched_rule_id is None
    assert exact_decision.permission_mode == PermissionMode.blocked
    assert exact_decision.matched_rule_id == high_priority_argument.id
    assert contains_decision.permission_mode == PermissionMode.approval_required
    assert contains_decision.matched_rule_id == contains.id
    assert [rule.id for rule in list_command_policy_rules()] == [
        disabled.id,
        high_priority_argument.id,
        executable.id,
        exact.id,
        contains.id,
    ]


def test_cli_runtime_honors_argument_aware_policy_rules(policy_state) -> None:
    from dgentic.cli_runtime import CliRuntimeService

    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Block force delete marker",
            match_type=CommandPolicyMatchType.argument_contains,
            pattern="force-delete",
            permission_mode=PermissionMode.blocked,
            reason="Force-delete marker is denied by policy.",
        )
    )

    service = CliRuntimeService()

    with pytest.raises(PermissionError, match="Force-delete marker"):
        service.execute_command(CommandExecutionRequest(command="cmd /c echo force-delete"))
