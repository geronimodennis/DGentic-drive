from dgentic.events import event_log
from dgentic.schemas import (
    LogEventType,
    PermissionMode,
    ProviderConfig,
    ProviderHealth,
    ProviderKind,
    RoutingDecision,
    RoutingRequest,
)

DEFAULT_PROVIDERS = [
    ProviderConfig(
        id="local-placeholder",
        name="Local Runtime Placeholder",
        kind=ProviderKind.local,
        base_url="http://127.0.0.1:11434",
        model_names=["local-default"],
        permission_mode=PermissionMode.autopilot_safe,
    ),
    ProviderConfig(
        id="external-placeholder",
        name="External Provider Placeholder",
        kind=ProviderKind.external,
        model_names=["external-default"],
        permission_mode=PermissionMode.approval_required,
    ),
]


def list_providers() -> list[ProviderConfig]:
    return list(DEFAULT_PROVIDERS)


def check_provider_health(provider_id: str) -> ProviderHealth:
    provider = next((item for item in DEFAULT_PROVIDERS if item.id == provider_id), None)
    health = ProviderHealth(
        provider_id=provider_id,
        available=provider is not None and provider.enabled,
        message="Provider is configured." if provider else "Provider is not configured.",
    )
    event_log.record(
        LogEventType.provider,
        "Checked provider health.",
        subject_id=provider_id,
        metadata=health.model_dump(mode="json"),
    )
    return health


def choose_provider(policy: RoutingRequest) -> RoutingDecision:
    enabled = [provider for provider in DEFAULT_PROVIDERS if provider.enabled]
    if policy.privacy_required:
        preferred = next(provider for provider in enabled if provider.kind == ProviderKind.local)
        reason = "Privacy requirement prefers the local runtime placeholder."
        score = 0.9
    else:
        preferred = enabled[0]
        reason = "Default routing prefers the first enabled provider until scoring is expanded."
        score = 0.6

    decision = RoutingDecision(
        provider_id=preferred.id,
        model_name=preferred.model_names[0] if preferred.model_names else None,
        reason=reason,
        score=score,
        policy=policy,
    )
    event_log.record(
        LogEventType.provider,
        "Selected provider route.",
        subject_id=preferred.id,
        metadata=decision.model_dump(mode="json"),
    )
    return decision
