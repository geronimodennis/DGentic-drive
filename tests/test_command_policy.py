import os

import pytest

from dgentic.command_policy import (
    create_command_policy_rule,
    evaluate_command_policy,
    list_command_policy_rules,
    parse_command,
    update_command_policy_rule,
)
from dgentic.events import event_log
from dgentic.orchestration import OrchestrationService
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandPolicyMatchType,
    CommandPolicyRequest,
    CommandPolicyRuleRequest,
    CommandPolicyRuleUpdate,
    LogEventType,
    OrchestrationCreateRequest,
    OrchestrationTaskSpec,
    OrchestrationTaskUpdate,
    PermissionMode,
    StepStatus,
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


def test_command_policy_keeps_legacy_agent_context_when_no_orchestration_task_matches(
    policy_state,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="cmd /c echo legacy context",
            agent_role="Developer",
            agent_id="legacy-agent",
            task_id="legacy-task",
        )
    )

    assert decision.permission_mode == PermissionMode.autopilot_safe
    assert decision.agent_id == "legacy-agent"
    assert decision.agent_role == "Developer"
    assert decision.task_id == "legacy-task"
    assert decision.orchestration is not None
    assert decision.orchestration.allowed is True
    assert (
        decision.orchestration.reason
        == "No active orchestration task matched supplied CLI context."
    )


@pytest.mark.parametrize(
    ("agent_id", "agent_role", "task_id", "reason"),
    [
        ("agent-from-task", None, None, "require agent_id, agent_role, and task_id"),
        (None, "QA", "qa-validation", "require agent_id, agent_role, and task_id"),
        ("wrong-agent", "QA", "qa-validation", "does not match the running orchestration task"),
        ("agent-from-task", "Developer", "qa-validation", "does not match orchestration task role"),
        ("agent-from-task", "QA", "wrong-task", "does not match the running orchestration task"),
    ],
)
def test_command_policy_fails_closed_for_partial_or_mismatched_active_orchestration_context(
    policy_state,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    reason: str,
) -> None:
    _root_dir, _data_dir = policy_state
    run = _create_running_orchestration_task()
    task = next(task for task in run.tasks if task.id == "qa-validation")
    bound_agent_id = task.agent_id if agent_id == "agent-from-task" else agent_id

    decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="cmd /c echo should-not-run",
            agent_role=agent_role,
            agent_id=bound_agent_id,
            task_id=task_id,
        )
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert reason in decision.reason
    assert decision.orchestration is not None
    assert decision.orchestration.allowed is False


def test_command_policy_allows_matching_orchestration_context_to_use_normal_policy(
    policy_state,
) -> None:
    _root_dir, _data_dir = policy_state
    run = _create_running_orchestration_task()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    safe_decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="cmd /c echo allowed",
            agent_role="qa",
            agent_id=task.agent_id,
            task_id=task.id,
        )
    )
    approval_decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="python --version",
            agent_role=task.role,
            agent_id=task.agent_id,
            task_id=task.id,
        )
    )

    assert safe_decision.permission_mode == PermissionMode.autopilot_safe
    assert safe_decision.orchestration is not None
    assert safe_decision.orchestration.allowed is True
    assert safe_decision.orchestration.run_id == run.id
    assert approval_decision.permission_mode == PermissionMode.approval_required
    assert approval_decision.orchestration is not None
    assert approval_decision.orchestration.allowed is True


def test_command_policy_blocks_known_non_running_cli_context(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    service = OrchestrationService()
    run = service.create_run(
        OrchestrationCreateRequest(
            objective="Reject stale CLI command policy context.",
            tasks=[
                OrchestrationTaskSpec(
                    id="qa-validation",
                    title="QA validation",
                    description="Validate stale orchestration-bound CLI behavior.",
                    role="QA",
                    declared_write_paths=["tests/test_command_policy.py"],
                    validation="Stale context is blocked.",
                )
            ],
        )
    )
    task = next(task for task in run.tasks if task.id == "qa-validation")
    service.update_task(
        run.id,
        task.id,
        OrchestrationTaskUpdate(status=StepStatus.completed, output={"tests": "passed"}),
    )

    decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="cmd /c echo stale-context",
            agent_role=task.role,
            agent_id=task.agent_id,
            task_id=task.id,
        )
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert decision.orchestration is not None
    assert decision.orchestration.allowed is False
    assert "not running" in decision.reason


def test_command_policy_serializes_orchestration_decision_metadata(policy_state) -> None:
    _root_dir, _data_dir = policy_state
    run = _create_running_orchestration_task()
    task = next(task for task in run.tasks if task.id == "qa-validation")

    decision = evaluate_command_policy(
        CommandPolicyRequest(
            command="cmd /c echo metadata",
            agent_role=task.role,
            agent_id=task.agent_id,
            task_id=task.id,
        )
    )
    serialized = decision.model_dump(mode="json")
    latest_event = event_log.list(LogEventType.cli)[-1]

    assert serialized["orchestration"] == {
        "allowed": True,
        "reason": "CLI action is bound to a running orchestration task.",
        "run_id": run.id,
        "task_id": task.id,
        "agent_id": task.agent_id,
        "agent_role": task.role,
        "violating_paths": [],
    }
    assert latest_event.metadata["orchestration"] == serialized["orchestration"]


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
            "cmd /d/s/c del important.txt",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "cmd /d/s/cdel important.txt",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "cmd /c=del important.txt",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
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
            "powershell -Com Remove-Item important.txt",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell /Com Remove-Item important.txt",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
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
        'cmd /c "start \\"title\\" cmd /d/s/cdel important.txt"',
        'cmd /c "start \\"title\\" cmd /c=del important.txt"',
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
    "command",
    [
        "cat ../secret.txt",
        "ls ../outside",
        "type /etc/passwd",
        "dir /etc",
        'bash -c "X=1 cat /etc/passwd"',
        'bash -c "HOME=/tmp cat $HOME/.ssh/config"',
        "bash -c \"cat $'/etc/passwd'\"",
        "bash -c \"cat $'/tmp'/secret.txt\"",
        'bash -c "cat ..{,/secret.txt}"',
        'bash -c "cat {../secret.txt,README}"',
        'bash -c "cat {~root,/tmp}/secret.txt"',
        "cat ~/secret",
        "cat $HOME/.ssh/config",
        'bash -c "cat ${HOME:-/tmp}/.ssh/config"',
        'sh -c "cat ${USER#prefix}/secret.txt"',
        "cmd /c cat ${!SECRET_PATH}/secret.txt",
        'bash -c "cat $TMP/secret.txt"',
        "cmd /c cat $TMP/secret.txt",
        'bash -c "cat ~root/.ssh/config"',
        'sh -c "ls ~nobody/.ssh"',
        "cmd /c type ~root/.ssh/config",
        r"get-childitem C:\Users\Public\secret.txt",
        r"cmd /c type %USERPROFILE:~0,3%\secret.txt",
        r"cmd /c type !USERPROFILE!\secret.txt",
        r"cmd /v:on /c type !USERPROFILE:~0,3!\secret.txt",
        r"cmd /v:on /c type !USERPROFILE:Users=Windows!\secret.txt",
        r"cmd /c type %ProgramFiles(x86)%\secret.txt",
        r"cmd /v:on /c type !ProgramFiles(x86)!\secret.txt",
        r"type %ProgramFiles(x86)%\secret.txt",
        r"cmd /c type ^C:\Users\Public\secret.txt",
        r"cmd /c type C^:\Users\Public\secret.txt",
        r"cmd /c type outside-^*",
        r"cmd /c type C:..\secret.txt",
        r"cmd /c type C:\workspace\..\secret.txt",
        r"type C:\workspace\..\secret.txt",
        r"cmd /c type ..\secret.txt",
        'bash -c "cat /etc/passwd"',
    ],
)
def test_read_only_commands_targeting_paths_outside_root_are_blocked(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason


def test_read_only_path_checks_allow_in_root_brace_expansion(policy_state) -> None:
    root_dir, _data_dir = policy_state
    (root_dir / "README").write_text("inside", encoding="utf-8")
    (root_dir / "docs").mkdir()

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "cat {README,docs}"'))

    assert decision.permission_mode == PermissionMode.autopilot_safe


def test_read_only_path_checks_block_glob_symlink_escapes(policy_state, tmp_path) -> None:
    root_dir, _data_dir = policy_state
    outside_file = tmp_path / "outside-secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    symlink = root_dir / "outside-link"
    symlink.symlink_to(outside_file)

    decision = evaluate_command_policy(CommandPolicyRequest(command='bash -c "cat outside-*"'))

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "dir /b",
        "dir /a:d",
        "dir /o:n",
        "type /?",
        "cmd /c dir /b",
        "cmd /c type /?",
    ],
)
def test_windows_slash_switches_are_not_treated_as_root_paths(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    expected_mode = PermissionMode.autopilot_safe if os.name == "nt" else PermissionMode.blocked
    assert decision.permission_mode == expected_mode


def test_read_only_path_checks_use_command_cwd(policy_state) -> None:
    root_dir, _data_dir = policy_state
    subdir = root_dir / "subdir"
    subdir.mkdir()
    inside_file = root_dir / "README.md"
    inside_file.write_text("inside", encoding="utf-8")

    decision = evaluate_command_policy(CommandPolicyRequest(command="cat ../README.md", cwd=subdir))

    assert decision.permission_mode == PermissionMode.autopilot_safe


def test_read_only_path_checks_block_cwd_relative_escapes(policy_state) -> None:
    root_dir, _data_dir = policy_state
    subdir = root_dir / "subdir"
    subdir.mkdir()

    decision = evaluate_command_policy(
        CommandPolicyRequest(command="cat ../outside.txt", cwd=root_dir)
    )
    subdir_decision = evaluate_command_policy(
        CommandPolicyRequest(command="cat ../../outside.txt", cwd=subdir)
    )

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason
    assert subdir_decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in subdir_decision.reason


def test_read_only_path_checks_block_symlink_escapes(policy_state, tmp_path) -> None:
    root_dir, _data_dir = policy_state
    outside_file = tmp_path / "outside-secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    symlink = root_dir / "outside-link"
    symlink.symlink_to(outside_file)

    decision = evaluate_command_policy(CommandPolicyRequest(command="cat outside-link"))

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason


def test_read_only_path_checks_block_quoted_symlink_with_spaces(
    policy_state,
    tmp_path,
) -> None:
    root_dir, _data_dir = policy_state
    outside_file = tmp_path / "outside secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    symlink = root_dir / "outside link"
    symlink.symlink_to(outside_file)

    decision = evaluate_command_policy(CommandPolicyRequest(command='cat "outside link"'))

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'cmd /c type "outside link"',
        'cmd /c cat "outside link"',
        'cmd /c dir "outside link"',
        'powershell -Command type "outside link"',
        'pwsh -c cat "outside link"',
    ],
)
def test_shell_wrappers_block_quoted_symlink_with_spaces(
    policy_state,
    tmp_path,
    command: str,
) -> None:
    root_dir, _data_dir = policy_state
    outside_file = tmp_path / "outside secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    symlink = root_dir / "outside link"
    symlink.symlink_to(outside_file)

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason


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


def test_configured_safe_rules_do_not_downgrade_out_of_root_read_only_paths(
    policy_state,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow cat",
            match_type=CommandPolicyMatchType.executable,
            pattern="cat",
            permission_mode=PermissionMode.autopilot_safe,
            reason="cat is usually read-only.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command="cat ../secret.txt"))

    assert decision.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "../outside-tool --version",
        r"..\outside-tool --version",
        "/bin/cat README.md",
        r"C:\Windows\System32\whoami.exe",
    ],
)
def test_executable_paths_outside_root_are_blocked(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert "executable path resolves outside configured rootDir" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'bash -c "/bin/cat README.md"',
        r"cmd /c ..\outside-tool --version",
        'powershell -Command "../outside-tool --version"',
        'powershell -Command "Start-Process -FilePath ../outside-tool -ArgumentList --version"',
    ],
)
def test_shell_wrapped_executable_paths_outside_root_are_blocked(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert "executable path resolves outside configured rootDir" in decision.reason


def test_configured_safe_rules_do_not_downgrade_executable_path_escapes(
    policy_state,
) -> None:
    _root_dir, _data_dir = policy_state
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow cat by basename",
            match_type=CommandPolicyMatchType.executable,
            pattern="cat",
            permission_mode=PermissionMode.autopilot_safe,
            reason="cat is usually read-only.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(CommandPolicyRequest(command="/bin/cat README.md"))

    assert decision.permission_mode == PermissionMode.blocked
    assert "executable path resolves outside configured rootDir" in decision.reason
    assert decision.matched_rule_id is None


def test_executable_paths_inside_root_keep_normal_policy_behavior(policy_state) -> None:
    root_dir, _data_dir = policy_state
    (root_dir / "scripts").mkdir()
    create_command_policy_rule(
        CommandPolicyRuleRequest(
            name="Allow workspace helper by basename",
            match_type=CommandPolicyMatchType.executable,
            pattern="safe-tool",
            permission_mode=PermissionMode.autopilot_safe,
            reason="Workspace helper is allowed.",
            priority=5,
        )
    )

    decision = evaluate_command_policy(
        CommandPolicyRequest(command="./scripts/safe-tool --version")
    )

    assert decision.permission_mode == PermissionMode.autopilot_safe
    assert decision.matched_rule_name == "Allow workspace helper by basename"


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
    ("command", "reason_fragment"),
    [
        ("bash -c \"r''m -rf important\"", "Inner shell command rm is blocked"),
        ('bash -c "r\\"\\"m -rf important"', "Inner shell command rm is blocked"),
        ("bash -c \"$'rm' -rf important\"", "Inner shell command rm is blocked"),
        ("bash -c \"$'r\\x6d' -rf important\"", "Inner shell command rm is blocked"),
        ("bash -c \"$'\\162\\155' -rf important\"", "Inner shell command rm is blocked"),
        ("bash -c \"$'r\\u006d' -rf important\"", "Inner shell command rm is blocked"),
        ("bash -c \"$'r\\U0000006d' -rf important\"", "Inner shell command rm is blocked"),
        ("cmd /c d^el important.txt", "Inner shell command del is blocked"),
        ('cmd /c d"e"l important.txt', "Inner shell command del is blocked"),
        ("cmd /c r^d /s /q important", "Inner shell command rd is blocked"),
        (
            "powershell -Command Remove-`Item important.txt",
            "Inner shell command remove-item is blocked",
        ),
        ("pwsh -Command r`m -rf important", "Inner shell command rm is blocked"),
        (
            "powershell -Command r`m im`portant.txt",
            "Inner shell command rm is blocked",
        ),
        (
            "powershell -Command Remove-`\nItem important.txt",
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -Command Remove-`\r\nItem important.txt",
            "Inner shell command remove-item is blocked",
        ),
        (
            "pwsh -Command r`\nm -rf important",
            "Inner shell command rm is blocked",
        ),
        (
            "pwsh -Command r`\r\nm -rf important",
            "Inner shell command rm is blocked",
        ),
        ('bash -c "r\\\nm -rf important"', "Inner shell command rm is blocked"),
        ('bash -c "r\\\r\nm -rf important"', "Inner shell command rm is blocked"),
        (
            "bash -c \"echo 'ok\\'; rm -rf important\"",
            "Inner shell command rm is blocked",
        ),
        (
            "powershell -Command \"Write-Output 'ok`'; Remove-Item important.txt\"",
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -Command \"Write-Output 'ok\\'; Remove-Item important.txt\"",
            "Inner shell command remove-item is blocked",
        ),
        (
            'powershell -Command "Write-Output ok\\; Remove-Item important.txt"',
            "Inner shell command remove-item is blocked",
        ),
    ],
)
def test_shell_command_name_escapes_do_not_hide_blocked_commands(
    policy_state,
    command: str,
    reason_fragment: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert reason_fragment in decision.reason


@pytest.mark.parametrize(
    ("command", "expected_mode", "reason_fragment"),
    [
        (
            'bash -c "echo ok" "rm -rf important"',
            PermissionMode.autopilot_safe,
            "low risk",
        ),
        (
            'sh -ec "echo ok" "rm -rf important"',
            PermissionMode.autopilot_safe,
            "low risk",
        ),
        (
            'bash -c "rm -rf important" echo',
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            "cmd /d /s /c del important.txt",
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        ("cmd /d /s /c echo hello", PermissionMode.autopilot_safe, "low risk"),
        (
            'cmd /c "echo ok ^& del important.txt"',
            PermissionMode.autopilot_safe if os.name == "nt" else PermissionMode.blocked,
            "low risk" if os.name == "nt" else "Inner shell command del is blocked",
        ),
        (
            'cmd /c "echo ok\\& del important.txt"',
            PermissionMode.blocked if os.name == "nt" else PermissionMode.autopilot_safe,
            "Inner shell command del is blocked" if os.name == "nt" else "low risk",
        ),
        (
            'cmd /c "echo ok & del important.txt"',
            PermissionMode.blocked,
            "Inner shell command del is blocked",
        ),
        (
            "powershell /Command Remove-Item important.txt",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -NoProfile -NonInteractive -Command Remove-Item important.txt",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "pwsh -NoProfile -NonInteractive -c rm important.txt",
            PermissionMode.blocked,
            "Inner shell command rm is blocked",
        ),
        (
            "pwsh -Command:Remove-Item important.txt",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -Command=Remove-Item important.txt",
            PermissionMode.blocked,
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -EncodedCommand AAAA",
            PermissionMode.approval_required,
            "no inspectable inner command",
        ),
        (
            "powershell -NoProfile -NonInteractive -EncodedCommand AAAA",
            PermissionMode.approval_required,
            "no inspectable inner command",
        ),
        (
            "powershell -File ./script.ps1",
            PermissionMode.approval_required,
            "no inspectable inner command",
        ),
        (
            "powershell -NoProfile -NonInteractive -File ./script.ps1",
            PermissionMode.approval_required,
            "no inspectable inner command",
        ),
    ],
)
def test_broader_windows_posix_shell_invocation_semantics(
    policy_state,
    command: str,
    expected_mode: PermissionMode,
    reason_fragment: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == expected_mode
    assert reason_fragment in decision.reason


def test_posix_translated_cmd_wrappers_use_posix_inner_semantics(
    policy_state,
    monkeypatch,
) -> None:
    _root_dir, _data_dir = policy_state
    monkeypatch.setattr("dgentic.command_policy._host_is_windows", lambda: False)

    escaped_control = evaluate_command_policy(
        CommandPolicyRequest(command='cmd /c "echo ok ^& rm -rf important"')
    )
    slash_path = evaluate_command_policy(CommandPolicyRequest(command="cmd /c dir /b"))

    assert escaped_control.permission_mode == PermissionMode.blocked
    assert "Inner shell command rm is blocked" in escaped_control.reason
    assert slash_path.permission_mode == PermissionMode.blocked
    assert "outside configured rootDir" in slash_path.reason


@pytest.mark.parametrize(
    ("command", "reason_fragment"),
    [
        (
            "powershell -Command \"Start-Process cmd '/c del important.txt'\"",
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process cmd -ArgumentList:/c,del important.txt"',
            "Inner shell command del is blocked",
        ),
        (
            "powershell -Command \"Start-Process -FilePath cmd '/c del important.txt'\"",
            "Inner shell command del is blocked",
        ),
        (
            'powershell -Command "Start-Process powershell -ArgumentList '
            "'-Command','Write-Output ok; Remove-Item important.txt'\"",
            "Inner shell command remove-item is blocked",
        ),
        (
            "powershell -Command \"Start-Process cmd -ArgumentList '/c','type ..\\secret.txt'\"",
            "outside configured rootDir",
        ),
    ],
)
def test_configured_safe_rules_do_not_downgrade_start_process_payload_blocks(
    policy_state,
    command: str,
    reason_fragment: str,
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
    assert reason_fragment in decision.reason


@pytest.mark.parametrize(
    ("command", "reason_fragment"),
    [
        (
            'powershell -Command "Start-Process powershell -ArgumentList '
            "'-EncodedCommand','AAAA'\"",
            "Launcher payload requires approval",
        ),
        (
            'powershell -Command "Start-Process python"',
            "Launcher payload requires approval",
        ),
    ],
)
def test_configured_safe_rules_do_not_downgrade_start_process_approval_payloads(
    policy_state,
    command: str,
    reason_fragment: str,
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

    assert decision.permission_mode == PermissionMode.approval_required
    assert reason_fragment in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'powershell -Command "try { Remove-Item important.txt } catch {}"',
        'powershell -Command "try { Write-Output ok } finally { Remove-Item important.txt }"',
        'powershell -Command "switch ($value) { default { Remove-Item important.txt } }"',
        'powershell -Command "trap { Remove-Item important.txt }"',
    ],
)
def test_powershell_script_block_flow_tokens_do_not_hide_blocked_commands(
    policy_state,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.blocked
    assert "Inner shell command remove-item is blocked" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        'cmd /c "type .d^gentic\\cli-approval-digest.key"',
        'powershell -Command "Get-ChildItem .d`gentic\\cli-approval-digest.key"',
    ],
)
def test_protected_state_file_detection_decodes_shell_escaped_paths(
    policy_state,
    monkeypatch,
    command: str,
) -> None:
    _root_dir, _data_dir = policy_state
    monkeypatch.setattr("dgentic.command_policy._host_is_windows", lambda: True)

    decision = evaluate_command_policy(CommandPolicyRequest(command=command))

    assert decision.permission_mode == PermissionMode.approval_required
    assert "DGentic state files" in decision.reason


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
                "SECRET=$(printf ASSIGNMENT_SECRET; echo ok) "
                "API_TOKEN=ps` assignment --refresh-token ps` value"
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
    assert "API_TOKEN=[REDACTED]" in redacted_command
    assert "--refresh-token [REDACTED]" in redacted_command
    assert "ps` assignment" not in redacted_command
    assert "ps` value" not in redacted_command


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
    assert executable_decision.permission_mode == PermissionMode.blocked
    assert "executable path resolves outside configured rootDir" in executable_decision.reason
    assert executable_decision.matched_rule_id is None
    assert scoped_out_decision.permission_mode == PermissionMode.blocked
    assert "executable path resolves outside configured rootDir" in scoped_out_decision.reason
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


def _create_running_orchestration_task():
    return OrchestrationService().create_run(
        OrchestrationCreateRequest(
            objective="Bind CLI command policy to a running QA task.",
            tasks=[
                OrchestrationTaskSpec(
                    id="qa-validation",
                    title="QA validation",
                    description="Validate orchestration-bound CLI behavior.",
                    role="QA",
                    declared_write_paths=["tests/test_command_policy.py"],
                    expected_output="Focused policy regressions.",
                    validation="pytest tests/test_command_policy.py passes.",
                )
            ],
        )
    )
