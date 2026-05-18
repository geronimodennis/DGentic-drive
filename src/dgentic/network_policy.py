import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from dgentic.events import event_log
from dgentic.hook_policy import evaluate_hook_policy
from dgentic.orchestration import (
    OrchestrationContextAuthorizationError,
    authorize_network_action,
)
from dgentic.redaction import redact_sensitive_values
from dgentic.schemas import (
    HookPolicyDecision,
    HookPolicySurface,
    LogEventType,
    NetworkPolicyRule,
    NetworkPolicyRuleRequest,
    NetworkPolicyRuleUpdate,
    PermissionMode,
)
from dgentic.settings import get_settings, managed_network_domain_policy_rules
from dgentic.storage import JsonCollection

NetworkPolicyMode = Literal["allow", "deny", "approval_required", "audit"]
NetworkPolicyRuleSource = Literal["local", "managed"]
DEFAULT_NETWORK_POLICY_MODE: NetworkPolicyMode = "allow"
DOMAIN_PATTERN = re.compile(r"^(?:\*\.)?[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")
NETWORK_APPROVAL_DIGEST_PREFIX = "hmac-sha256:"
REDACTED_LEGACY_DIGEST_MARKER = "[LEGACY_DIGEST_REDACTED]"
DEFAULT_NETWORK_APPROVAL_TTL_MINUTES = 30
MAX_NETWORK_CONTEXT_FIELD_CHARS = 256
MAX_NETWORK_LABEL_CHARS = 64
_NETWORK_APPROVAL_DIGEST_KEY_FILE = "network-approval-digest.key"
_NETWORK_APPROVAL_DIGEST_LOCK = Lock()
_network_approval_lock = Lock()
_NETWORK_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
_network_policy_rules = JsonCollection("network-domain-policy-rules", NetworkPolicyRule)


class NetworkDomainPolicyError(ValueError):
    """Raised when network domain policy configuration is malformed."""


class NetworkApprovalRequiredError(PermissionError):
    """Raised when a network request requires an approved bound approval record."""


class NetworkApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    executed = "executed"


@dataclass(frozen=True)
class NetworkDomainPolicyDecision:
    url: str
    host: str
    mode: NetworkPolicyMode
    matched_domain: str | None = None
    matched_rule_id: str | None = None
    matched_rule_source: NetworkPolicyRuleSource | None = None
    reason: str = ""
    hook_policy: HookPolicyDecision | None = None

    @property
    def allowed(self) -> bool:
        return self.mode in {"allow", "audit"}


@dataclass(frozen=True)
class NetworkDomainRule:
    domain: str
    mode: NetworkPolicyMode
    reason: str = ""
    id: str | None = None
    source: NetworkPolicyRuleSource = "local"
    priority: int = 100
    enabled: bool = True


@dataclass(frozen=True)
class NetworkDomainPolicy:
    default_mode: NetworkPolicyMode = DEFAULT_NETWORK_POLICY_MODE
    rules: tuple[NetworkDomainRule, ...] = ()


class NetworkApproval(BaseModel):
    id: str
    url: str
    scheme: str
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    path: str = ""
    surface: str = Field(default="provider", max_length=MAX_NETWORK_LABEL_CHARS)
    action: str = Field(default="request", max_length=MAX_NETWORK_LABEL_CHARS)
    mode: NetworkPolicyMode = "approval_required"
    matched_domain: str | None = None
    policy_reason: str = ""
    permission_mode: PermissionMode = PermissionMode.approval_required
    url_digest: str = ""
    policy_digest: str = ""
    approval_digest: str = ""
    status: NetworkApprovalStatus = NetworkApprovalStatus.pending
    requested_by: str | None = Field(default=None, max_length=MAX_NETWORK_CONTEXT_FIELD_CHARS)
    agent_id: str | None = Field(default=None, max_length=MAX_NETWORK_CONTEXT_FIELD_CHARS)
    agent_role: str | None = Field(default=None, max_length=MAX_NETWORK_CONTEXT_FIELD_CHARS)
    task_id: str | None = Field(default=None, max_length=MAX_NETWORK_CONTEXT_FIELD_CHARS)
    decided_by: str | None = Field(default=None, max_length=MAX_NETWORK_CONTEXT_FIELD_CHARS)
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: (
            datetime.now(UTC) + timedelta(minutes=DEFAULT_NETWORK_APPROVAL_TTL_MINUTES)
        )
    )
    decided_at: datetime | None = None
    executed_at: datetime | None = None

    @field_validator("surface", "action")
    @classmethod
    def labels_must_be_bounded(cls, value: str) -> str:
        return _normalize_approval_label(value)

    def model_post_init(self, __context: object) -> None:
        self.url = redact_sensitive_values(self.url)
        self.path = redact_sensitive_values(self.path)
        self.policy_reason = redact_sensitive_values(self.policy_reason)
        self.requested_by = _redact_optional_sensitive_text(self.requested_by)
        self.agent_id = _redact_optional_sensitive_text(self.agent_id)
        self.agent_role = _redact_optional_sensitive_text(self.agent_role)
        self.task_id = _redact_optional_sensitive_text(self.task_id)
        self.decided_by = _redact_optional_sensitive_text(self.decided_by)
        self.decision_reason = _redact_optional_sensitive_text(self.decision_reason)
        self.denial_reason = _redact_optional_sensitive_text(self.denial_reason)
        self.url_digest = _sanitize_network_approval_digest(self.url_digest)
        self.policy_digest = _sanitize_network_approval_digest(self.policy_digest)
        self.approval_digest = _sanitize_network_approval_digest(self.approval_digest)


class NetworkApprovalReview(BaseModel):
    id: str
    status: NetworkApprovalStatus
    url: str
    scheme: str
    host: str
    port: int | None = None
    path: str = ""
    surface: str
    action: str
    mode: NetworkPolicyMode
    matched_domain: str | None = None
    policy_reason: str = ""
    permission_mode: PermissionMode
    url_digest: str = ""
    policy_digest: str = ""
    approval_digest: str = ""
    requested_by: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None
    task_id: str | None = None
    requires_bound_execution_request: bool = True
    direct_execute_available: bool = False
    review_warnings: list[str] = Field(default_factory=list)
    decided_by: str | None = None
    decision_reason: str | None = None
    denial_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    executed_at: datetime | None = None


_network_approvals = JsonCollection("network-approvals", NetworkApproval)


def create_network_policy_rule(
    request: NetworkPolicyRuleRequest,
    *,
    actor: str | None = None,
) -> NetworkPolicyRule:
    payload = _normalized_network_policy_rule_payload(request)
    rule = NetworkPolicyRule(
        id=f"netpolicy-{uuid4()}",
        **payload,
    )
    _network_policy_rules.upsert(rule)
    _record_network_policy_rule_event("Created network domain policy rule.", rule, actor=actor)
    return rule


def list_network_policy_rules() -> list[NetworkPolicyRule]:
    return _combined_network_policy_rules()


def update_network_policy_rule(
    rule_id: str,
    update: NetworkPolicyRuleUpdate,
    *,
    actor: str | None = None,
) -> NetworkPolicyRule | None:
    if _managed_network_policy_rule(rule_id) is not None:
        raise PermissionError(
            "Managed network domain policy rules cannot be modified through the API."
        )
    rule = _network_policy_rules.get(rule_id)
    if rule is None:
        return None

    updates = update.model_dump(exclude_unset=True)
    preview = rule.model_copy(update=updates)
    payload = _normalized_network_policy_rule_payload(
        NetworkPolicyRuleRequest(
            domain=preview.domain,
            mode=preview.mode,
            reason=preview.reason,
            enabled=preview.enabled,
            priority=preview.priority,
        )
    )
    for field, value in payload.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(UTC)
    _network_policy_rules.upsert(rule)
    _record_network_policy_rule_event("Updated network domain policy rule.", rule, actor=actor)
    return rule


def evaluate_network_domain_policy(
    url: str,
    *,
    settings: Any | None = None,
    actor: str | None = None,
    action: str = "request",
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
) -> NetworkDomainPolicyDecision:
    active_settings = settings if settings is not None else get_settings()
    host = _host_for_url(url)
    policy = network_domain_policy(active_settings)

    for rule in policy.rules:
        if _domain_matches(host, rule.domain):
            return _apply_hook_policy_to_network_decision(
                NetworkDomainPolicyDecision(
                    url=url,
                    host=host,
                    mode=rule.mode,
                    matched_domain=rule.domain,
                    matched_rule_id=rule.id,
                    matched_rule_source=rule.source,
                    reason=rule.reason or _default_rule_reason(rule),
                ),
                actor=actor,
                action=action,
                agent_id=agent_id,
                agent_role=agent_role,
                task_id=task_id,
            )

    return _apply_hook_policy_to_network_decision(
        NetworkDomainPolicyDecision(
            url=url,
            host=host,
            mode=policy.default_mode,
            reason=f"Used default network domain policy mode: {policy.default_mode}.",
        ),
        actor=actor,
        action=action,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )


def _apply_hook_policy_to_network_decision(
    decision: NetworkDomainPolicyDecision,
    *,
    actor: str | None,
    action: str,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> NetworkDomainPolicyDecision:
    current_permission_mode = _permission_mode_for_network_mode(decision.mode)
    hook_decision = evaluate_hook_policy(
        surface=HookPolicySurface.network,
        action=action,
        subject=decision.url,
        current_permission_mode=current_permission_mode,
        agent_role=agent_role,
        agent_id=agent_id,
        task_id=task_id,
        actor=actor,
    )
    if hook_decision is None:
        return decision
    mode = decision.mode
    reason = decision.reason
    if decision.mode != "deny":
        if hook_decision.permission_mode == PermissionMode.blocked:
            mode = "deny"
            reason = hook_decision.reason
        elif (
            hook_decision.permission_mode == PermissionMode.approval_required
            and decision.mode in {"allow", "audit"}
        ):
            mode = "approval_required"
            reason = hook_decision.reason
    return NetworkDomainPolicyDecision(
        url=decision.url,
        host=decision.host,
        mode=mode,
        matched_domain=decision.matched_domain,
        matched_rule_id=decision.matched_rule_id,
        matched_rule_source=decision.matched_rule_source,
        reason=reason,
        hook_policy=hook_decision,
    )


def _permission_mode_for_network_mode(mode: NetworkPolicyMode) -> PermissionMode:
    if mode == "deny":
        return PermissionMode.blocked
    if mode == "approval_required":
        return PermissionMode.approval_required
    return PermissionMode.autopilot_safe


def network_domain_policy(settings: Any | None = None) -> NetworkDomainPolicy:
    active_settings = settings if settings is not None else get_settings()
    managed_rules = tuple(
        NetworkDomainRule(
            id=record.id,
            domain=record.domain,
            mode=record.mode,
            reason=record.reason,
            enabled=record.enabled,
            priority=record.priority,
            source="managed",
        )
        for record in managed_network_domain_policy_rules(active_settings)
        if record.enabled
    )
    persisted_rules = tuple(
        NetworkDomainRule(
            id=record.id,
            domain=record.domain,
            mode=record.mode,
            reason=record.reason,
            enabled=record.enabled,
            priority=record.priority,
            source=record.source,
        )
        for record in _local_network_policy_rules()
        if record.enabled
    )
    raw_config = active_settings.network_domain_policy.strip()
    if not raw_config:
        return NetworkDomainPolicy(rules=(*managed_rules, *persisted_rules))
    try:
        payload = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise NetworkDomainPolicyError("Network domain policy must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise NetworkDomainPolicyError("Network domain policy must be a JSON object.")

    default_mode = _normalize_mode(payload.get("default_mode", DEFAULT_NETWORK_POLICY_MODE))
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, list):
        raise NetworkDomainPolicyError("Network domain policy rules must be a list.")

    rules = tuple(_parse_rule(rule) for rule in raw_rules)
    return NetworkDomainPolicy(
        default_mode=default_mode,
        rules=(*managed_rules, *rules, *persisted_rules),
    )


def create_network_approval(
    url: str,
    *,
    surface: str = "provider",
    action: str = "request",
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkApproval:
    active_settings = settings if settings is not None else get_settings()
    _authorize_network_context_or_raise(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    decision = evaluate_network_domain_policy(
        url,
        settings=active_settings,
        actor=requested_by,
        action=action,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    if decision.mode != "approval_required":
        raise ValueError("Only approval-required network requests can be queued.")

    parts = _url_parts_for_approval(url)
    surface_value = _normalize_approval_label(surface)
    action_value = _normalize_approval_label(action)
    url_digest = network_url_digest(url)
    policy_digest = network_policy_decision_digest(decision, settings=active_settings)
    approval_digest = network_approval_digest(
        url_digest=url_digest,
        policy_digest=policy_digest,
        surface=surface_value,
        action=action_value,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        permission_mode=PermissionMode.approval_required,
    )
    approval = NetworkApproval(
        id=f"network-approval-{uuid4()}",
        url=_safe_url_for_review(parts),
        scheme=parts.scheme.lower(),
        host=(parts.hostname or "").lower().rstrip("."),
        port=parts.port,
        path=redact_sensitive_values(parts.path or ""),
        surface=surface_value,
        action=action_value,
        mode=decision.mode,
        matched_domain=decision.matched_domain,
        policy_reason=decision.reason,
        permission_mode=PermissionMode.approval_required,
        url_digest=url_digest,
        policy_digest=policy_digest,
        approval_digest=approval_digest,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    _network_approvals.upsert(approval)
    event_log.record(
        LogEventType.approval,
        "Created network approval request.",
        actor=approval.requested_by or "system",
        subject_id=approval.id,
        metadata={
            "url": approval.url,
            "scheme": approval.scheme,
            "host": approval.host,
            "port": approval.port,
            "path": approval.path,
            "surface": approval.surface,
            "action": approval.action,
            "mode": approval.mode,
            "matched_domain": approval.matched_domain,
            "permission_mode": approval.permission_mode,
            "requested_by": approval.requested_by,
            "agent_id": approval.agent_id,
            "agent_role": approval.agent_role,
            "task_id": approval.task_id,
            "url_digest": approval.url_digest,
            "policy_digest": approval.policy_digest,
            "approval_digest": approval.approval_digest,
            "expires_at": approval.expires_at.isoformat(),
        },
    )
    return approval


def list_network_approvals(
    status: NetworkApprovalStatus | str | None = None,
) -> list[NetworkApproval]:
    approvals = _network_approvals.list()
    if status is None:
        return approvals
    requested_status = NetworkApprovalStatus(status)
    return [approval for approval in approvals if approval.status == requested_status]


def get_network_approval(approval_id: str) -> NetworkApproval:
    return _get_network_approval_or_raise(approval_id)


def get_network_approval_review(approval_id: str) -> NetworkApprovalReview:
    approval = _get_network_approval_or_raise(approval_id)
    warnings = [
        "Network approval stores a sanitized URL preview and request digests; execute with "
        "a bound request for the same surface, action, URL, policy, and actor context."
    ]
    if _network_approval_is_expired(approval):
        warnings.append("Approval is expired.")
    return NetworkApprovalReview(
        id=approval.id,
        status=approval.status,
        url=approval.url,
        scheme=approval.scheme,
        host=approval.host,
        port=approval.port,
        path=approval.path,
        surface=approval.surface,
        action=approval.action,
        mode=approval.mode,
        matched_domain=approval.matched_domain,
        policy_reason=approval.policy_reason,
        permission_mode=approval.permission_mode,
        url_digest=approval.url_digest,
        policy_digest=approval.policy_digest,
        approval_digest=approval.approval_digest,
        requested_by=approval.requested_by,
        agent_id=approval.agent_id,
        agent_role=approval.agent_role,
        task_id=approval.task_id,
        direct_execute_available=False,
        review_warnings=warnings,
        decided_by=approval.decided_by,
        decision_reason=_redact_optional_sensitive_text(approval.decision_reason),
        denial_reason=_redact_optional_sensitive_text(approval.denial_reason),
        created_at=approval.created_at,
        updated_at=approval.updated_at,
        expires_at=approval.expires_at,
        decided_at=approval.decided_at,
        executed_at=approval.executed_at,
    )


def approve_network_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> NetworkApproval:
    redacted_reason = _redact_optional_sensitive_text(reason)

    def approve(current: NetworkApproval) -> NetworkApproval:
        if current.status != NetworkApprovalStatus.pending:
            raise ValueError(
                "Only pending network approvals can be approved; "
                f"current status is {current.status}."
            )
        if _network_approval_is_expired(current):
            raise ValueError(f"Network approval {approval_id} has expired and cannot be approved.")

        now = datetime.now(UTC)
        current.status = NetworkApprovalStatus.approved
        current.decided_by = _redact_optional_sensitive_text(decided_by)
        current.decision_reason = redacted_reason
        current.decided_at = now
        current.updated_at = now
        return current

    approval = _network_approvals.update(approval_id, approve)
    event_log.record(
        LogEventType.approval,
        "Approved network request.",
        subject_id=approval.id,
        actor=approval.decided_by or "system",
        metadata={
            "url": approval.url,
            "host": approval.host,
            "surface": approval.surface,
            "action": approval.action,
            **({"reason": redacted_reason} if redacted_reason else {}),
        },
    )
    return approval


def deny_network_approval(
    approval_id: str,
    *,
    decided_by: str | None = None,
    reason: str | None = None,
) -> NetworkApproval:
    redacted_reason = _redact_optional_sensitive_text(reason)

    def deny(current: NetworkApproval) -> NetworkApproval:
        if current.status != NetworkApprovalStatus.pending:
            raise ValueError(
                f"Only pending network approvals can be denied; current status is {current.status}."
            )

        now = datetime.now(UTC)
        current.status = NetworkApprovalStatus.denied
        current.decided_by = _redact_optional_sensitive_text(decided_by)
        current.decision_reason = redacted_reason
        current.denial_reason = redacted_reason
        current.decided_at = now
        current.updated_at = now
        return current

    approval = _network_approvals.update(approval_id, deny)
    event_log.record(
        LogEventType.approval,
        "Denied network request.",
        subject_id=approval.id,
        actor=approval.decided_by or "system",
        metadata={
            "url": approval.url,
            "host": approval.host,
            "surface": approval.surface,
            "action": approval.action,
            **({"reason": redacted_reason} if redacted_reason else {}),
        },
    )
    return approval


def validate_bound_network_approval(
    approval_id: str,
    *,
    url: str,
    surface: str = "provider",
    action: str = "request",
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkApproval:
    _authorize_network_context_or_raise(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    try:
        approval = _get_network_approval_or_raise(approval_id)
    except KeyError as exc:
        raise NetworkApprovalRequiredError(str(exc)) from exc
    _validate_bound_network_approval(
        approval,
        url=url,
        surface=surface,
        action=action,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        settings=settings,
    )
    return approval


def claim_network_approval(
    approval_id: str,
    *,
    url: str,
    surface: str = "provider",
    action: str = "request",
    requested_by: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    task_id: str | None = None,
    settings: Any | None = None,
) -> NetworkApproval:
    _authorize_network_context_or_raise(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )

    def claim(current: NetworkApproval) -> NetworkApproval:
        _validate_bound_network_approval(
            current,
            url=url,
            surface=surface,
            action=action,
            requested_by=requested_by,
            agent_id=agent_id,
            agent_role=agent_role,
            task_id=task_id,
            settings=settings,
        )
        now = datetime.now(UTC)
        current.status = NetworkApprovalStatus.executed
        current.executed_at = now
        current.updated_at = now
        return current

    with _network_approval_lock:
        try:
            approval = _network_approvals.update(approval_id, claim)
        except KeyError as exc:
            raise NetworkApprovalRequiredError(str(exc)) from exc
    event_log.record(
        LogEventType.approval,
        "Claimed network approval for execution.",
        actor=requested_by or approval.requested_by or "system",
        subject_id=approval.id,
        metadata={
            "url": approval.url,
            "host": approval.host,
            "surface": approval.surface,
            "action": approval.action,
            "requested_by": _redact_optional_sensitive_text(requested_by),
        },
    )
    return approval


def network_url_digest(url: str) -> str:
    parts = _url_parts_for_approval(url)
    return _network_hmac_digest(_canonical_json(_canonical_url_for_binding(parts)))


def safe_network_url_for_review(url: str) -> str:
    return _safe_url_for_review(_url_parts_for_approval(url))


def network_policy_decision_digest(
    decision: NetworkDomainPolicyDecision,
    *,
    settings: Any | None = None,
) -> str:
    active_settings = settings if settings is not None else get_settings()
    return _network_hmac_digest(
        _canonical_json(
            {
                "network_policy_revision": network_policy_revision_digest(active_settings),
                "host": decision.host,
                "mode": decision.mode,
                "matched_domain": decision.matched_domain,
                "matched_rule_id": decision.matched_rule_id,
                "matched_rule_source": decision.matched_rule_source,
                "reason": decision.reason,
                "hook_policy": (
                    decision.hook_policy.model_dump(mode="json")
                    if decision.hook_policy is not None
                    else None
                ),
            }
        )
    )


def network_policy_revision_digest(settings: Any | None = None) -> str:
    active_settings = settings if settings is not None else get_settings()
    policy = network_domain_policy(active_settings)
    return _network_hmac_digest(
        _canonical_json(
            {
                "schema_version": 1,
                "default_mode": policy.default_mode,
                "rules": [
                    {
                        "id": rule.id,
                        "source": rule.source,
                        "domain": rule.domain,
                        "mode": rule.mode,
                        "priority": rule.priority,
                        "reason": rule.reason,
                    }
                    for rule in policy.rules
                ],
            }
        )
    )


def network_approval_digest(
    *,
    url_digest: str,
    policy_digest: str,
    surface: str,
    action: str,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    permission_mode: PermissionMode,
) -> str:
    payload = {
        "url_digest": url_digest,
        "policy_digest": policy_digest,
        "surface": _normalize_approval_label(surface),
        "action": _normalize_approval_label(action),
        "requested_by": requested_by,
        "agent_id": agent_id,
        "agent_role": agent_role,
        "task_id": task_id,
        "permission_mode": permission_mode,
    }
    return _network_hmac_digest(_canonical_json(payload))


def _normalized_network_policy_rule_payload(request: NetworkPolicyRuleRequest) -> dict[str, Any]:
    return {
        "domain": _normalize_domain(request.domain),
        "mode": _normalize_mode(request.mode),
        "reason": redact_sensitive_values(request.reason.strip()),
        "enabled": request.enabled,
        "priority": request.priority,
    }


def _local_network_policy_rules() -> list[NetworkPolicyRule]:
    return _sort_network_policy_rule_records(_network_policy_rules.list())


def _combined_network_policy_rules() -> list[NetworkPolicyRule]:
    managed_rules = [
        NetworkPolicyRule(
            id=record.id,
            domain=record.domain,
            mode=record.mode,
            reason=record.reason,
            enabled=record.enabled,
            priority=record.priority,
            source="managed",
            created_at=datetime(1970, 1, 1, tzinfo=UTC),
            updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        )
        for record in managed_network_domain_policy_rules()
    ]
    managed_ids = {rule.id for rule in managed_rules}
    local_rules = [rule for rule in _network_policy_rules.list() if rule.id not in managed_ids]
    return [
        *managed_rules,
        *_sort_network_policy_rule_records(local_rules),
    ]


def _managed_network_policy_rule(rule_id: str) -> NetworkPolicyRule | None:
    for record in managed_network_domain_policy_rules():
        if record.id == rule_id:
            return NetworkPolicyRule(
                id=record.id,
                domain=record.domain,
                mode=record.mode,
                reason=record.reason,
                enabled=record.enabled,
                priority=record.priority,
                source="managed",
                created_at=datetime(1970, 1, 1, tzinfo=UTC),
                updated_at=datetime(1970, 1, 1, tzinfo=UTC),
            )
    return None


def _sort_network_policy_rule_records(
    rules: list[NetworkPolicyRule],
) -> list[NetworkPolicyRule]:
    return sorted(rules, key=_network_policy_rule_sort_key)


def _network_policy_rule_sort_key(rule: NetworkPolicyRule) -> tuple[int, bool, int, datetime, str]:
    specificity_domain = rule.domain[2:] if rule.domain.startswith("*.") else rule.domain
    return (
        rule.priority,
        rule.domain.startswith("*."),
        -len(specificity_domain),
        rule.created_at,
        rule.id,
    )


def _record_network_policy_rule_event(
    message: str,
    rule: NetworkPolicyRule,
    *,
    actor: str | None,
) -> None:
    event_log.record(
        LogEventType.network,
        message,
        actor=actor or "system",
        subject_id=rule.id,
        metadata=rule.model_dump(mode="json"),
    )


def _parse_rule(raw_rule: Any) -> NetworkDomainRule:
    if not isinstance(raw_rule, dict):
        raise NetworkDomainPolicyError("Network domain policy rule must be an object.")
    domain = _normalize_domain(raw_rule.get("domain"))
    mode = _normalize_mode(raw_rule.get("mode"))
    reason = raw_rule.get("reason", "")
    if reason is None:
        reason = ""
    if not isinstance(reason, str):
        raise NetworkDomainPolicyError("Network domain policy rule reason must be a string.")
    return NetworkDomainRule(domain=domain, mode=mode, reason=reason.strip())


def _default_rule_reason(rule: NetworkDomainRule) -> str:
    if rule.source == "managed" and rule.id:
        return f"Matched managed network domain policy rule {rule.id} for {rule.domain}."
    return f"Matched network domain policy rule for {rule.domain}."


def _normalize_mode(value: Any) -> NetworkPolicyMode:
    if not isinstance(value, str):
        raise NetworkDomainPolicyError("Network domain policy mode must be a string.")
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"allow", "deny", "approval_required", "audit"}:
        raise NetworkDomainPolicyError("Network domain policy mode is not supported.")
    return normalized  # type: ignore[return-value]


def _normalize_domain(value: Any) -> str:
    if not isinstance(value, str):
        raise NetworkDomainPolicyError("Network domain policy rule domain must be a string.")
    domain = value.strip().lower().rstrip(".")
    if not domain or "/" in domain or ":" in domain or not DOMAIN_PATTERN.fullmatch(domain):
        raise NetworkDomainPolicyError("Network domain policy rule domain is not valid.")
    if ".." in domain:
        raise NetworkDomainPolicyError("Network domain policy rule domain is not valid.")
    return domain


def _host_for_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise NetworkDomainPolicyError("Network policy URL is not valid.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise NetworkDomainPolicyError("Network policy URL must use http or https with a host.")
    return parts.hostname.lower().rstrip(".")


def _domain_matches(host: str, domain: str) -> bool:
    if domain.startswith("*."):
        suffix = domain[2:]
        return host.endswith(f".{suffix}") and host != suffix
    return host == domain


def _authorize_network_context_or_raise(
    *,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
) -> None:
    decision = authorize_network_action(
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    if not decision.allowed:
        raise OrchestrationContextAuthorizationError(decision.reason)


def _validate_bound_network_approval(
    approval: NetworkApproval,
    *,
    url: str,
    surface: str,
    action: str,
    requested_by: str | None,
    agent_id: str | None,
    agent_role: str | None,
    task_id: str | None,
    settings: Any | None,
) -> None:
    if approval.status != NetworkApprovalStatus.approved:
        raise NetworkApprovalRequiredError(
            f"Network approval {approval.id} is not executable; current status is "
            f"{approval.status}."
        )
    if _network_approval_is_expired(approval):
        raise NetworkApprovalRequiredError(
            f"Network approval {approval.id} has expired and cannot be executed."
        )

    active_settings = settings if settings is not None else get_settings()
    decision = evaluate_network_domain_policy(
        url,
        settings=active_settings,
        actor=requested_by,
        action=action,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
    )
    if decision.mode != "approval_required":
        raise NetworkApprovalRequiredError(
            f"Network approval {approval.id} is not required by the current network policy."
        )

    parts = _url_parts_for_approval(url)
    surface_value = _normalize_approval_label(surface)
    action_value = _normalize_approval_label(action)
    url_digest = network_url_digest(url)
    policy_digest = network_policy_decision_digest(decision, settings=active_settings)
    expected_approval_digest = network_approval_digest(
        url_digest=url_digest,
        policy_digest=policy_digest,
        surface=surface_value,
        action=action_value,
        requested_by=requested_by,
        agent_id=agent_id,
        agent_role=agent_role,
        task_id=task_id,
        permission_mode=PermissionMode.approval_required,
    )
    checks = [
        approval.url == _safe_url_for_review(parts),
        approval.scheme == parts.scheme.lower(),
        approval.host == (parts.hostname or "").lower().rstrip("."),
        approval.port == parts.port,
        approval.path == redact_sensitive_values(parts.path or ""),
        approval.surface == surface_value,
        approval.action == action_value,
        approval.mode == decision.mode,
        approval.matched_domain == decision.matched_domain,
        approval.policy_reason == redact_sensitive_values(decision.reason),
        approval.permission_mode == PermissionMode.approval_required,
        approval.url_digest == url_digest,
        approval.policy_digest == policy_digest,
        approval.approval_digest == expected_approval_digest,
        approval.requested_by == _redact_optional_sensitive_text(requested_by),
        approval.agent_id == _redact_optional_sensitive_text(agent_id),
        approval.agent_role == _redact_optional_sensitive_text(agent_role),
        approval.task_id == _redact_optional_sensitive_text(task_id),
    ]
    if not all(checks):
        raise NetworkApprovalRequiredError(
            f"Network approval {approval.id} is not bound to this network request."
        )


def _network_approval_is_expired(approval: NetworkApproval) -> bool:
    return approval.expires_at <= datetime.now(UTC)


def _get_network_approval_or_raise(approval_id: str) -> NetworkApproval:
    approval = _network_approvals.get(approval_id)
    if approval is None:
        raise KeyError(f"Network approval not found: {approval_id}")
    return approval


def _url_parts_for_approval(url: str) -> SplitResult:
    try:
        parts = urlsplit(url.strip())
        _ = parts.port
    except ValueError as exc:
        raise NetworkDomainPolicyError("Network policy URL is not valid.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise NetworkDomainPolicyError("Network policy URL must use http or https with a host.")
    if parts.username or parts.password:
        raise NetworkDomainPolicyError("Network approval URL must not include credentials.")
    return parts


def _canonical_url_for_binding(parts: SplitResult) -> dict[str, Any]:
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": parts.path or "",
        "query": parts.query or "",
        "fragment": parts.fragment or "",
    }


def _safe_url_for_review(parts: SplitResult) -> str:
    netloc = _netloc_for_parts(parts)
    return redact_sensitive_values(
        urlunsplit((parts.scheme.lower(), netloc, parts.path or "", "", ""))
    )


def _netloc_for_parts(parts: SplitResult) -> str:
    host = (parts.hostname or "").lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parts.port
    if port is not None:
        return f"{host}:{port}"
    return host


def _normalize_approval_label(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Network approval labels must be strings.")
    normalized = value.strip().lower()
    if not normalized or not _NETWORK_LABEL_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Network approval labels must start with a lowercase letter or digit and contain "
            "only lowercase letters, digits, underscores, hyphens, dots, or colons."
        )
    return normalized


def _redact_optional_sensitive_text(text: str | None) -> str | None:
    if text is None:
        return None
    return redact_sensitive_values(text)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _network_hmac_digest(payload: str) -> str:
    return (
        NETWORK_APPROVAL_DIGEST_PREFIX
        + hmac.new(
            _network_approval_digest_key(),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )


def _network_approval_digest_key() -> bytes:
    settings = get_settings()
    configured_key = settings.approval_digest_key.strip()
    if configured_key:
        return configured_key.encode("utf-8")

    data_dir = settings.data_dir
    if not data_dir.is_absolute():
        data_dir = settings.root_dir / data_dir
    key_path = data_dir / _NETWORK_APPROVAL_DIGEST_KEY_FILE
    with _NETWORK_APPROVAL_DIGEST_LOCK:
        if key_path.exists():
            stored_key = key_path.read_text(encoding="utf-8").strip()
            if stored_key:
                return stored_key.encode("utf-8")
        key_path.parent.mkdir(parents=True, exist_ok=True)
        generated_key = secrets.token_hex(32)
        key_path.write_text(generated_key + "\n", encoding="utf-8")
        return generated_key.encode("utf-8")


def _sanitize_network_approval_digest(digest: str) -> str:
    if not digest:
        return ""
    if digest.startswith(NETWORK_APPROVAL_DIGEST_PREFIX):
        suffix = digest.removeprefix(NETWORK_APPROVAL_DIGEST_PREFIX)
        if len(suffix) == 64 and all(char in "0123456789abcdef" for char in suffix):
            return digest
    return REDACTED_LEGACY_DIGEST_MARKER
