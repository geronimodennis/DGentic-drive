from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

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


def create_hook_policy_rule(
    request: HookPolicyRuleRequest,
    *,
    actor: str | None = None,
) -> HookPolicyRule:
    rule = HookPolicyRule(
        id=f"hookpolicy-{uuid4()}",
        name=redact_sensitive_values(request.name),
        surface=request.surface,
        action=_normalize_action(request.action),
        match_type=request.match_type,
        pattern=_stored_pattern(request.surface, request.match_type, request.pattern),
        effect=request.effect,
        reason=redact_sensitive_values(request.reason),
        agent_roles=_normalize_agent_roles(request.agent_roles),
        enabled=request.enabled,
        priority=request.priority,
    )
    _hook_policy_rules.upsert(rule)
    event_log.record(
        LogEventType.hook,
        "Created hook policy rule.",
        actor=actor or "system",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )
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
    event_log.record(
        LogEventType.hook,
        "Updated hook policy rule.",
        actor=actor or "system",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )
    return rule


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
