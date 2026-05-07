import pytest

from dgentic.command_policy import (
    create_command_policy_rule,
    evaluate_command_policy,
    list_command_policy_rules,
    update_command_policy_rule,
)
from dgentic.schemas import (
    CommandExecutionRequest,
    CommandPolicyMatchType,
    CommandPolicyRequest,
    CommandPolicyRuleRequest,
    CommandPolicyRuleUpdate,
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
