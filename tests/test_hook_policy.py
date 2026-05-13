import json

import pytest

from dgentic.events import event_log
from dgentic.hook_policy import (
    PluginHookPolicyInstallRequest,
    create_hook_policy_rule,
    evaluate_hook_policy,
    install_plugin_hook_policy_rule,
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


def test_managed_hook_policy_rules_precede_local_rules_and_stay_out_of_state(
    hook_policy_state,
    monkeypatch,
) -> None:
    data_dir = hook_policy_state
    managed_path = data_dir.parent / "managed-settings.json"
    managed_path.write_text(
        json.dumps(
            {
                "settings": {
                    "managed_hook_policy_rules": [
                        {
                            "id": "managed.block-deploy",
                            "name": "Managed block deploy",
                            "surface": "command",
                            "action": "execute",
                            "match_type": "contains",
                            "pattern": "deploy",
                            "effect": "blocked",
                            "reason": "Managed hook blocks deploy.",
                            "priority": 100,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", str(managed_path))
    get_settings.cache_clear()
    local_rule = create_hook_policy_rule(
        HookPolicyRuleRequest(
            name="Local audit deploy",
            surface=HookPolicySurface.command,
            action="execute",
            match_type=HookPolicyMatchType.contains,
            pattern="deploy",
            effect=HookPolicyEffect.audit,
            reason="Local hook audits deploy.",
            priority=0,
        )
    )

    decision = evaluate_hook_policy(
        surface=HookPolicySurface.command,
        action="execute",
        subject="python deploy.py",
        current_permission_mode=PermissionMode.autopilot_safe,
    )
    rules = list_hook_policy_rules()
    persisted = json.loads((data_dir / "hook-policy-rules.json").read_text(encoding="utf-8"))

    assert decision is not None
    assert decision.permission_mode == PermissionMode.blocked
    assert decision.matched_rule_id == "managed.block-deploy"
    assert [rule.id for rule in rules] == ["managed.block-deploy", local_rule.id]
    assert rules[0].source == "managed"
    assert rules[1].source == "local"
    assert [rule["id"] for rule in persisted] == [local_rule.id]


def test_disabled_and_role_scoped_managed_hook_policy_rules(
    hook_policy_state,
    monkeypatch,
) -> None:
    data_dir = hook_policy_state
    managed_path = data_dir.parent / "managed-settings.json"
    managed_path.write_text(
        json.dumps(
            {
                "settings": {
                    "managed_hook_policy_rules": [
                        {
                            "id": "managed.disabled-block",
                            "name": "Disabled managed hook",
                            "surface": "command",
                            "action": "execute",
                            "match_type": "contains",
                            "pattern": "deploy",
                            "effect": "blocked",
                            "reason": "Disabled managed hook should not match.",
                            "enabled": False,
                            "priority": 1,
                        },
                        {
                            "id": "managed.qa-block",
                            "name": "Managed QA hook",
                            "surface": "command",
                            "action": "execute",
                            "match_type": "contains",
                            "pattern": "deploy",
                            "effect": "blocked",
                            "reason": "QA deploys require a separate workflow.",
                            "agent_roles": [" QA ", "qa"],
                            "priority": 5,
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", str(managed_path))
    get_settings.cache_clear()

    developer_decision = evaluate_hook_policy(
        surface=HookPolicySurface.command,
        action="execute",
        subject="python deploy.py",
        current_permission_mode=PermissionMode.autopilot_safe,
        agent_role="developer",
    )
    qa_decision = evaluate_hook_policy(
        surface=HookPolicySurface.command,
        action="execute",
        subject="python deploy.py",
        current_permission_mode=PermissionMode.autopilot_safe,
        agent_role="QA",
    )
    rules = list_hook_policy_rules()

    assert developer_decision is None
    assert qa_decision is not None
    assert qa_decision.permission_mode == PermissionMode.blocked
    assert qa_decision.matched_rule_id == "managed.qa-block"
    assert [rule.id for rule in rules] == ["managed.disabled-block", "managed.qa-block"]
    assert rules[1].agent_roles == ["qa"]


def test_managed_hook_policy_rules_are_read_only_and_do_not_downgrade_blocked_decisions(
    hook_policy_state,
    monkeypatch,
) -> None:
    data_dir = hook_policy_state
    managed_path = data_dir.parent / "managed-settings.json"
    managed_path.write_text(
        json.dumps(
            {
                "settings": {
                    "managed_hook_policy_rules": [
                        {
                            "id": "managed.audit-blocked",
                            "name": "Managed audit blocked",
                            "surface": "command",
                            "action": "execute",
                            "match_type": "contains",
                            "pattern": "deploy",
                            "effect": "audit",
                            "reason": "Managed hook cannot downgrade blocked decisions.",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", str(managed_path))
    get_settings.cache_clear()

    decision = evaluate_hook_policy(
        surface=HookPolicySurface.command,
        action="execute",
        subject="python deploy.py",
        current_permission_mode=PermissionMode.blocked,
    )

    assert decision is not None
    assert decision.permission_mode == PermissionMode.blocked
    assert decision.allowed is False
    assert decision.matched_rule_id == "managed.audit-blocked"
    with pytest.raises(PermissionError, match="Managed hook policy"):
        update_hook_policy_rule(
            "managed.audit-blocked",
            HookPolicyRuleUpdate(enabled=False),
        )


def test_managed_hook_policy_rule_ids_block_plugin_install_collisions(
    hook_policy_state,
    monkeypatch,
) -> None:
    data_dir = hook_policy_state
    managed_path = data_dir.parent / "managed-settings.json"
    managed_path.write_text(
        json.dumps(
            {
                "settings": {
                    "managed_hook_policy_rules": [
                        {
                            "id": "managed.collision",
                            "name": "Managed collision",
                            "surface": "command",
                            "action": "execute",
                            "match_type": "contains",
                            "pattern": "deploy",
                            "effect": "blocked",
                            "reason": "Managed rule owns this id.",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DGENTIC_MANAGED_SETTINGS_FILE", str(managed_path))
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="id is managed"):
        install_plugin_hook_policy_rule(
            PluginHookPolicyInstallRequest(
                rule_id="managed.collision",
                rule=HookPolicyRuleRequest(
                    name="Plugin collision",
                    surface=HookPolicySurface.command,
                    action="execute",
                    match_type=HookPolicyMatchType.contains,
                    pattern="deploy",
                    effect=HookPolicyEffect.audit,
                    reason="Plugin should not shadow managed rules.",
                ),
                plugin_id="collision-plugin",
                manifest_digest="a" * 64,
                component_path="hooks/deploy.json",
                component_digest="b" * 64,
            )
        )


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
