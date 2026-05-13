import json

import pytest

from dgentic.events import event_log
from dgentic.hook_policy import (
    create_hook_policy_rule,
    evaluate_hook_policy,
    list_hook_policy_rules,
    update_hook_policy_rule,
)
from dgentic.schemas import (
    HookPolicyEffect,
    HookPolicyMatchType,
    HookPolicyRuleRequest,
    HookPolicyRuleUpdate,
    HookPolicySurface,
    LogEventType,
    PermissionMode,
)
from dgentic.settings import get_settings


@pytest.fixture()
def hook_policy_state(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    data_dir = tmp_path / "state"
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    yield data_dir
    get_settings.cache_clear()


def test_hook_policy_persists_redacts_sorts_and_matches_context(hook_policy_state) -> None:
    lower_priority = create_hook_policy_rule(
        HookPolicyRuleRequest(
            name="Audit command",
            surface=HookPolicySurface.command,
            action="execute",
            match_type=HookPolicyMatchType.contains,
            pattern="deploy",
            effect=HookPolicyEffect.audit,
            reason="Audit deployment.",
            priority=50,
        ),
        actor="operator",
    )
    higher_priority = create_hook_policy_rule(
        HookPolicyRuleRequest(
            name="Sensitive TOKEN=hook-secret",
            surface=HookPolicySurface.command,
            action=" EXECUTE ",
            match_type=HookPolicyMatchType.contains,
            pattern="deploy",
            effect=HookPolicyEffect.approval_required,
            reason="Review TOKEN=hook-secret",
            agent_roles=[" QA ", "qa"],
            priority=5,
        ),
        actor="operator TOKEN=hook-secret",
    )

    decision = evaluate_hook_policy(
        surface=HookPolicySurface.command,
        action="execute",
        subject="python deploy.py --password super-secret",
        current_permission_mode=PermissionMode.autopilot_safe,
        agent_role="qa",
        agent_id="agent TOKEN=hook-secret",
        task_id="task PASSWORD=hook-secret",
        actor="operator",
    )
    non_matching_role = evaluate_hook_policy(
        surface=HookPolicySurface.command,
        action="execute",
        subject="python deploy.py",
        current_permission_mode=PermissionMode.autopilot_safe,
        agent_role="developer",
    )

    rules = list_hook_policy_rules()
    persisted = (hook_policy_state / "hook-policy-rules.json").read_text(encoding="utf-8")
    hook_logs = json.dumps(
        [event.model_dump(mode="json") for event in event_log.list(LogEventType.hook)]
    )

    assert [rule.id for rule in rules] == [higher_priority.id, lower_priority.id]
    assert higher_priority.name == "Sensitive TOKEN=[REDACTED]"
    assert higher_priority.reason == "Review TOKEN=[REDACTED]"
    assert higher_priority.agent_roles == ["qa"]
    assert decision is not None
    assert decision.permission_mode == PermissionMode.approval_required
    assert decision.matched_rule_id == higher_priority.id
    assert "super-secret" not in decision.subject
    assert non_matching_role is not None
    assert non_matching_role.effect == HookPolicyEffect.audit
    assert "hook-secret" not in persisted
    assert "hook-secret" not in hook_logs
    assert "TOKEN=[REDACTED]" in persisted
    assert "TOKEN=[REDACTED]" in hook_logs


def test_hook_policy_update_disable_and_effect_escalation(hook_policy_state) -> None:
    audit_rule = create_hook_policy_rule(
        HookPolicyRuleRequest(
            name="Audit target",
            surface=HookPolicySurface.filesystem,
            action="*",
            match_type=HookPolicyMatchType.contains,
            pattern="target",
            effect=HookPolicyEffect.audit,
            reason="Audit target path.",
            priority=20,
        )
    )
    blocking_rule = create_hook_policy_rule(
        HookPolicyRuleRequest(
            name="Block target prefix",
            surface=HookPolicySurface.filesystem,
            action="write",
            match_type=HookPolicyMatchType.prefix,
            pattern="target",
            effect=HookPolicyEffect.blocked,
            reason="Block target path.",
            priority=1,
        )
    )

    blocked = evaluate_hook_policy(
        surface=HookPolicySurface.filesystem,
        action="write",
        subject="target/file.txt",
        current_permission_mode=PermissionMode.approval_required,
    )
    update_hook_policy_rule(blocking_rule.id, HookPolicyRuleUpdate(enabled=False))
    audited = evaluate_hook_policy(
        surface=HookPolicySurface.filesystem,
        action="write",
        subject="target/file.txt",
        current_permission_mode=PermissionMode.autopilot_safe,
    )
    update_hook_policy_rule(
        audit_rule.id,
        HookPolicyRuleUpdate(
            match_type=HookPolicyMatchType.exact,
            pattern="target/file.txt",
            effect=HookPolicyEffect.approval_required,
        ),
    )
    approval = evaluate_hook_policy(
        surface=HookPolicySurface.filesystem,
        action="read",
        subject="target/file.txt",
        current_permission_mode=PermissionMode.autopilot_safe,
    )

    assert blocked is not None
    assert blocked.permission_mode == PermissionMode.blocked
    assert blocked.allowed is False
    assert audited is not None
    assert audited.effect == HookPolicyEffect.audit
    assert audited.permission_mode == PermissionMode.autopilot_safe
    assert audited.allowed is True
    assert approval is not None
    assert approval.permission_mode == PermissionMode.approval_required


def test_hook_policy_rejects_secret_shaped_match_patterns(hook_policy_state) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        HookPolicyRuleRequest(
            name=" ",
            surface=HookPolicySurface.command,
            action="execute",
            match_type=HookPolicyMatchType.any,
            effect=HookPolicyEffect.audit,
            reason="Blank names are invalid.",
        )

    request = HookPolicyRuleRequest(
        name="Secret pattern",
        surface=HookPolicySurface.command,
        action="execute",
        match_type=HookPolicyMatchType.contains,
        pattern="TOKEN=raw-secret",
        effect=HookPolicyEffect.blocked,
        reason="Reject secret-shaped patterns.",
    )

    with pytest.raises(ValueError, match="stable non-secret"):
        create_hook_policy_rule(request)

    rule = create_hook_policy_rule(
        HookPolicyRuleRequest(
            name="Safe pattern",
            surface=HookPolicySurface.network,
            action="request",
            match_type=HookPolicyMatchType.contains,
            pattern="https://api.example.test/private",
            effect=HookPolicyEffect.blocked,
            reason="Block private API.",
        )
    )

    with pytest.raises(ValueError, match="query strings"):
        update_hook_policy_rule(
            rule.id,
            HookPolicyRuleUpdate(pattern="https://api.example.test/private?page=1"),
        )

    assert (
        not (hook_policy_state / "hook-policy-rules.json")
        .read_text(encoding="utf-8")
        .count("raw-secret")
    )
