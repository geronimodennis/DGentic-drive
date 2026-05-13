from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, Field

from dgentic.events import event_log
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import (
    HookPolicyDecision,
    HookPolicyEffect,
    HookPolicyMatchType,
    HookPolicyRule,
    HookPolicyRuleRequest,
    HookPolicyRuleUpdate,
    HookPolicySurface,
    LogEventType,
    PermissionMode,
)
from dgentic.storage import JsonCollection

_hook_policy_rules = JsonCollection("hook-policy-rules", HookPolicyRule)
MAX_HOOK_SUBJECT_CHARS = 500


class PluginHookPolicyInstallRequest(BaseModel):
    rule_id: str = Field(min_length=1, max_length=120)
    rule: HookPolicyRuleRequest
    plugin_id: str = Field(min_length=1, max_length=80)
    manifest_digest: str = Field(min_length=64, max_length=64)
    component_path: str = Field(min_length=1, max_length=300)
    component_digest: str = Field(min_length=64, max_length=64)


def create_hook_policy_rule(
    request: HookPolicyRuleRequest,
    *,
    actor: str | None = None,
) -> HookPolicyRule:
    payload = _normalized_rule_payload(request)
    rule = HookPolicyRule(
        id=f"hookpolicy-{uuid4()}",
        **payload,
    )
    _hook_policy_rules.upsert(rule)
    _record_hook_policy_event("Created hook policy rule.", rule, actor=actor)
    return rule


def list_hook_policy_rules() -> list[HookPolicyRule]:
    return _sorted_rules(_hook_policy_rules.list())


def update_hook_policy_rule(
    rule_id: str,
    update: HookPolicyRuleUpdate,
    *,
    actor: str | None = None,
) -> HookPolicyRule | None:
    rule = _hook_policy_rules.get(rule_id)
    if rule is None:
        return None
    if rule.source == "plugin":
        raise PermissionError("Plugin-owned hook policy rules must be managed through plugins.")

    updates = update.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = redact_sensitive_values(updates["name"])
    if "action" in updates and updates["action"] is not None:
        updates["action"] = _normalize_action(updates["action"])
    if "pattern" in updates and updates["pattern"] is not None:
        updates["pattern"] = updates["pattern"].strip()
    if "reason" in updates and updates["reason"] is not None:
        updates["reason"] = redact_sensitive_values(updates["reason"])
    if "agent_roles" in updates and updates["agent_roles"] is not None:
        updates["agent_roles"] = _normalize_agent_roles(updates["agent_roles"])

    preview = rule.model_copy(update=updates)
    HookPolicyRuleRequest(
        name=preview.name,
        surface=preview.surface,
        action=preview.action,
        match_type=preview.match_type,
        pattern=preview.pattern,
        effect=preview.effect,
        reason=preview.reason,
        agent_roles=preview.agent_roles,
        enabled=preview.enabled,
        priority=preview.priority,
    )
    updates["pattern"] = _stored_pattern(preview.surface, preview.match_type, preview.pattern)
    for field, value in updates.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(UTC)
    _hook_policy_rules.upsert(rule)
    _record_hook_policy_event("Updated hook policy rule.", rule, actor=actor)
    return rule


def validate_hook_policy_rule_request(request: HookPolicyRuleRequest) -> HookPolicyRuleRequest:
    payload = _normalized_rule_payload(request)
    return HookPolicyRuleRequest(**payload)


def install_plugin_hook_policy_rule(
    request: PluginHookPolicyInstallRequest,
    *,
    actor: str | None = None,
) -> HookPolicyRule:
    now = datetime.now(UTC)
    payload = _normalized_rule_payload(request.rule)
    rule = HookPolicyRule(
        id=request.rule_id,
        **payload,
        source="plugin",
        source_plugin_id=request.plugin_id,
        source_plugin_manifest_digest=request.manifest_digest,
        source_plugin_component_path=request.component_path,
        source_plugin_component_digest=request.component_digest,
        source_plugin_status="active",
        created_at=now,
        updated_at=now,
    )

    def upsert(items: list[HookPolicyRule]) -> tuple[list[HookPolicyRule], HookPolicyRule]:
        updated_items: list[HookPolicyRule] = []
        replaced = False
        created_at = now
        for item in items:
            if item.id != rule.id:
                updated_items.append(item)
                continue
            if item.source != "plugin" or item.source_plugin_id != rule.source_plugin_id:
                raise ValueError(f"Hook policy rule id is already in use: {rule.id}")
            created_at = item.created_at
            updated_items.append(rule.model_copy(update={"created_at": created_at}))
            replaced = True
        saved = rule.model_copy(update={"created_at": created_at})
        if not replaced:
            updated_items.append(saved)
        return updated_items, saved

    saved = _hook_policy_rules.transact(upsert)
    _record_hook_policy_event("Installed plugin hook policy rule.", saved, actor=actor)
    return saved


def disable_plugin_hook_policy_rules(
    plugin_id: str,
    *,
    actor: str | None = None,
) -> list[HookPolicyRule]:
    now = datetime.now(UTC)
    disabled: list[HookPolicyRule] = []

    def disable(items: list[HookPolicyRule]) -> tuple[list[HookPolicyRule], list[HookPolicyRule]]:
        updated_items: list[HookPolicyRule] = []
        for item in items:
            if item.source == "plugin" and item.source_plugin_id == plugin_id:
                updated = item.model_copy(
                    update={
                        "enabled": False,
                        "source_plugin_status": "disabled",
                        "updated_at": now,
                    }
                )
                updated_items.append(updated)
                disabled.append(updated)
            else:
                updated_items.append(item)
        return updated_items, disabled

    saved = _hook_policy_rules.transact(disable)
    for rule in saved:
        _record_hook_policy_event("Disabled plugin hook policy rule.", rule, actor=actor)
    return saved


def evaluate_hook_policy(
    *,
    surface: HookPolicySurface,
    action: str,
    subject: str,
    current_permission_mode: PermissionMode,
    agent_role: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
    actor: str | None = None,
) -> HookPolicyDecision | None:
    normalized_action = _normalize_action(action)
    raw_subject = subject.strip()
    safe_subject = _safe_subject_for_surface(surface, raw_subject)
    for rule in _sorted_rules(_hook_policy_rules.list()):
        if not rule.enabled:
            continue
        if rule.source == "plugin" and rule.source_plugin_status != "active":
            continue
        if rule.surface != surface:
            continue
        if rule.action != "*" and rule.action != normalized_action:
            continue
        if not _rule_applies_to_context(rule, agent_role):
            continue
        if not _rule_matches(rule, raw_subject):
            continue
        decision = _decision_from_rule(
            rule,
            action=normalized_action,
            subject=safe_subject,
            current_permission_mode=current_permission_mode,
        )
        event_log.record(
            LogEventType.hook,
            "Matched hook policy rule.",
            actor=actor or "system",
            subject_id=rule.id,
            metadata={
                **decision.model_dump(mode="json"),
                "agent_id": redact_sensitive_values(agent_id or ""),
                "agent_role": redact_sensitive_values(agent_role or ""),
                "task_id": redact_sensitive_values(task_id or ""),
            },
        )
        return decision
    return None


def _normalized_rule_payload(request: HookPolicyRuleRequest) -> dict:
    return {
        "name": redact_sensitive_values(request.name),
        "surface": request.surface,
        "action": _normalize_action(request.action),
        "match_type": request.match_type,
        "pattern": _stored_pattern(request.surface, request.match_type, request.pattern),
        "effect": request.effect,
        "reason": redact_sensitive_values(request.reason),
        "agent_roles": _normalize_agent_roles(request.agent_roles),
        "enabled": request.enabled,
        "priority": request.priority,
    }


def _record_hook_policy_event(
    message: str,
    rule: HookPolicyRule,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.hook,
        message,
        actor=actor or "system",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )


def _decision_from_rule(
    rule: HookPolicyRule,
    *,
    action: str,
    subject: str,
    current_permission_mode: PermissionMode,
) -> HookPolicyDecision:
    permission_mode = current_permission_mode
    allowed = current_permission_mode != PermissionMode.blocked
    if rule.effect == HookPolicyEffect.blocked:
        permission_mode = PermissionMode.blocked
        allowed = False
    elif (
        rule.effect == HookPolicyEffect.approval_required
        and current_permission_mode == PermissionMode.autopilot_safe
    ):
        permission_mode = PermissionMode.approval_required
        allowed = False
    return HookPolicyDecision(
        surface=rule.surface,
        action=action,
        subject=subject,
        effect=rule.effect,
        permission_mode=permission_mode,
        allowed=allowed,
        reason=rule.reason,
        matched_rule_id=rule.id,
        matched_rule_name=rule.name,
    )


def _sorted_rules(rules: list[HookPolicyRule]) -> list[HookPolicyRule]:
    return sorted(rules, key=lambda rule: (rule.priority, rule.created_at, rule.id))


def _rule_applies_to_context(rule: HookPolicyRule, agent_role: str | None) -> bool:
    if not rule.agent_roles:
        return True
    if agent_role is None:
        return False
    return agent_role.strip().lower() in rule.agent_roles


def _rule_matches(rule: HookPolicyRule, subject: str) -> bool:
    if rule.match_type == HookPolicyMatchType.any:
        return True
    pattern = rule.pattern.lower()
    normalized_subject = " ".join(subject.lower().split())
    if rule.match_type == HookPolicyMatchType.exact:
        return normalized_subject == " ".join(pattern.split())
    if rule.match_type == HookPolicyMatchType.contains:
        return pattern in subject.lower()
    if rule.match_type == HookPolicyMatchType.prefix:
        return subject.lower().startswith(pattern)
    return False


def _normalize_action(action: str) -> str:
    return action.strip().lower() or "*"


def _normalize_agent_roles(agent_roles: list[str]) -> list[str]:
    return sorted({role.strip().lower() for role in agent_roles if role.strip()})


def _stored_pattern(
    surface: HookPolicySurface,
    match_type: HookPolicyMatchType,
    pattern: str,
) -> str:
    value = pattern.strip()
    if match_type == HookPolicyMatchType.any:
        return redact_sensitive_values(value)
    redacted = redact_sensitive_values(value)
    if redacted != value:
        raise ValueError(
            "Hook policy patterns must use stable non-secret match values; "
            "secret-shaped values cannot be persisted safely."
        )
    if surface == HookPolicySurface.network and ("?" in value or "#" in value):
        raise ValueError(
            "Network hook policy patterns must not include query strings or fragments."
        )
    return value


def _safe_subject_for_surface(surface: HookPolicySurface, subject: str) -> str:
    if surface == HookPolicySurface.network:
        return _safe_network_subject(subject)
    return _truncate_subject(redact_sensitive_values(subject))


def _safe_network_subject(subject: str) -> str:
    try:
        parts = urlsplit(subject)
        port = parts.port
    except ValueError:
        return _truncate_subject(redact_sensitive_values(subject))
    if not parts.scheme or not parts.hostname:
        return _truncate_subject(redact_sensitive_values(subject))
    netloc = parts.hostname.lower().rstrip(".")
    if port is not None:
        netloc = f"{netloc}:{port}"
    safe_path = redact_sensitive_values(parts.path or "")
    return _truncate_subject(urlunsplit((parts.scheme.lower(), netloc, safe_path, "", "")))


def _truncate_subject(subject: str) -> str:
    if len(subject) <= MAX_HOOK_SUBJECT_CHARS:
        return subject
    return f"{subject[:MAX_HOOK_SUBJECT_CHARS]}..."
