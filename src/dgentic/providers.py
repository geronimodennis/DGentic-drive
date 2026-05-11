from os import environ
from typing import Any
from urllib.error import URLError

from dgentic.events import event_log
from dgentic.provider_policy import (
    ProviderEgressPolicyError,
    normalize_provider_base_url,
    validate_provider_base_url,
)
from dgentic.provider_runtime import EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID
from dgentic.provider_transport import (
    ProviderRetryPolicy,
    ProviderTransportRequest,
    send_provider_json_request,
)
from dgentic.schemas import (
    LogEventType,
    PermissionMode,
    ProviderConfig,
    ProviderHealth,
    ProviderKind,
    RoutingDecision,
    RoutingRequest,
)
from dgentic.settings import get_settings

MODEL_PROBE_TIMEOUT_SECONDS = 1.5


class ProviderRoutingError(ValueError):
    """Raised when no provider can satisfy the requested routing policy."""


def default_providers() -> list[ProviderConfig]:
    settings = get_settings()
    external_enabled = _external_provider_configured(settings)
    return [
        ProviderConfig(
            id="ollama",
            name="Ollama",
            kind=ProviderKind.local,
            base_url=_safe_provider_base_url_for_display(settings.ollama_base_url),
            model_names=[],
            capabilities=["chat", "local", "private"],
            estimated_latency_ms=250,
            estimated_cost_usd=0.0,
            permission_mode=PermissionMode.autopilot_safe,
            supports_streaming=False,
        ),
        ProviderConfig(
            id="lm-studio",
            name="LM Studio",
            kind=ProviderKind.local,
            base_url=_safe_provider_base_url_for_display(settings.lm_studio_base_url),
            model_names=[],
            capabilities=["chat", "streaming", "local", "openai-compatible", "private"],
            estimated_latency_ms=300,
            estimated_cost_usd=0.0,
            permission_mode=PermissionMode.autopilot_safe,
            supports_streaming=True,
        ),
        ProviderConfig(
            id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            name="OpenAI-Compatible External",
            kind=ProviderKind.external,
            base_url=_safe_external_provider_base_url_for_display(settings),
            model_names=_external_model_names(settings) if external_enabled else [],
            capabilities=["chat", "streaming", "external", "openai-compatible", "high-capability"],
            estimated_latency_ms=800,
            estimated_cost_usd=0.01,
            permission_mode=PermissionMode.approval_required,
            enabled=external_enabled,
            supports_streaming=True,
        ),
        ProviderConfig(
            id="external-placeholder",
            name="External Provider Placeholder",
            kind=ProviderKind.external,
            model_names=[],
            capabilities=["chat", "external", "high-capability"],
            estimated_latency_ms=800,
            estimated_cost_usd=0.01,
            permission_mode=PermissionMode.approval_required,
            enabled=False,
            supports_streaming=False,
        ),
    ]


def list_providers() -> list[ProviderConfig]:
    providers = []
    for provider in default_providers():
        health = check_provider_health(provider.id)
        providers.append(provider.model_copy(update={"model_names": health.model_names}))
    return providers


def check_provider_health(provider_id: str) -> ProviderHealth:
    provider = next((item for item in default_providers() if item.id == provider_id), None)
    if provider is None:
        health = ProviderHealth(
            provider_id=provider_id,
            available=False,
            message="Provider is not configured.",
        )
    elif provider.id == "ollama":
        health = _probe_ollama(provider)
    elif provider.id == "lm-studio":
        health = _probe_lm_studio(provider)
    elif provider.id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID:
        health = _check_external_openai_compatible(provider)
    else:
        health = ProviderHealth(
            provider_id=provider.id,
            available=False,
            message="Provider adapter is not implemented yet and is not routable.",
            model_names=[],
        )
    event_log.record(
        LogEventType.provider,
        "Checked provider health.",
        subject_id=provider_id,
        metadata=health.model_dump(mode="json"),
    )
    return health


def choose_provider(policy: RoutingRequest) -> RoutingDecision:
    providers = list_providers()
    scored = {provider.id: _score_provider(provider, policy) for provider in providers}
    if not any(score > 0 for score in scored.values()):
        raise ProviderRoutingError("No provider satisfies the requested routing policy.")
    preferred = max(providers, key=lambda provider: scored[provider.id])
    score = scored[preferred.id]

    if policy.privacy_required and preferred.kind == ProviderKind.local:
        reason = "Privacy requirement selected the highest-scoring local provider."
    elif preferred.estimated_cost_usd == 0:
        reason = "Routing selected the lowest-cost capable provider."
    else:
        reason = "Routing selected the highest-scoring provider for the requested policy."

    decision = RoutingDecision(
        provider_id=preferred.id,
        model_name=preferred.model_names[0] if preferred.model_names else None,
        reason=reason,
        score=score,
        policy=policy,
        candidate_scores=scored,
    )
    event_log.record(
        LogEventType.provider,
        "Selected provider route.",
        subject_id=preferred.id,
        metadata=decision.model_dump(mode="json"),
    )
    return decision


def _score_provider(provider: ProviderConfig, policy: RoutingRequest) -> float:
    if not provider.enabled:
        return 0.0
    if policy.privacy_required and provider.kind == ProviderKind.external:
        return 0.0

    score = 0.0
    capabilities = set(provider.capabilities)
    required = set(policy.required_capabilities)

    if required and not required.issubset(capabilities):
        return 0.0

    score += 0.2
    if provider.model_names:
        score += 0.2
    if policy.privacy_required and provider.kind == ProviderKind.local:
        score += 0.3
    if not policy.privacy_required:
        score += 0.1
    if required:
        score += 0.2 * (len(required.intersection(capabilities)) / len(required))
    else:
        score += 0.1
    if policy.max_latency_ms and provider.estimated_latency_ms:
        score += 0.1 if provider.estimated_latency_ms <= policy.max_latency_ms else -0.1
    if policy.max_cost_usd is not None and provider.estimated_cost_usd is not None:
        score += 0.1 if provider.estimated_cost_usd <= policy.max_cost_usd else -0.2
    if provider.permission_mode == PermissionMode.autopilot_safe:
        score += 0.1

    return round(max(score, 0.0), 3)


def _probe_ollama(provider: ProviderConfig) -> ProviderHealth:
    try:
        settings = get_settings()
        base_url = validate_provider_base_url(
            provider_id=provider.id,
            base_url=settings.ollama_base_url,
        )
        payload = _get_json(f"{base_url}/api/tags")
        model_names = [model["name"] for model in payload.get("models", []) if "name" in model]
        return ProviderHealth(
            provider_id=provider.id,
            available=True,
            message="Ollama is reachable.",
            model_names=model_names,
        )
    except (OSError, URLError, TimeoutError) as exc:
        return ProviderHealth(
            provider_id=provider.id,
            available=False,
            message=f"Ollama is not reachable: {exc}",
        )


def _probe_lm_studio(provider: ProviderConfig) -> ProviderHealth:
    try:
        settings = get_settings()
        base_url = validate_provider_base_url(
            provider_id=provider.id,
            base_url=settings.lm_studio_base_url,
        )
        payload = _get_json(f"{base_url}/v1/models")
        model_names = [model["id"] for model in payload.get("data", []) if "id" in model]
        return ProviderHealth(
            provider_id=provider.id,
            available=True,
            message="LM Studio is reachable.",
            model_names=model_names,
        )
    except (OSError, URLError, TimeoutError) as exc:
        return ProviderHealth(
            provider_id=provider.id,
            available=False,
            message=f"LM Studio is not reachable: {exc}",
        )


def _get_json(url: str) -> dict:
    result = send_provider_json_request(
        ProviderTransportRequest(
            url=url,
            method="GET",
            timeout_seconds=MODEL_PROBE_TIMEOUT_SECONDS,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
    )
    return result.payload


def _safe_provider_base_url_for_display(base_url: str) -> str | None:
    if not base_url.strip():
        return None
    try:
        return normalize_provider_base_url(base_url)
    except ProviderEgressPolicyError:
        return None


def _safe_external_provider_base_url_for_display(settings: Any) -> str | None:
    normalized = _safe_provider_base_url_for_display(settings.external_openai_compatible_base_url)
    if normalized is None or not normalized.startswith("https://"):
        return None
    return normalized


def _check_external_openai_compatible(provider: ProviderConfig) -> ProviderHealth:
    if not provider.enabled:
        return ProviderHealth(
            provider_id=provider.id,
            available=False,
            message="External provider is not configured.",
            model_names=[],
        )
    return ProviderHealth(
        provider_id=provider.id,
        available=True,
        message="External provider is configured.",
        model_names=provider.model_names,
    )


def _external_provider_configured(settings: Any) -> bool:
    credential_env = settings.external_openai_compatible_api_key_env.strip()
    return (
        bool(_safe_external_provider_base_url_for_display(settings))
        and bool(credential_env)
        and bool(environ.get(credential_env, "").strip())
        and bool(_external_model_names(settings))
    )


def _external_model_names(settings: Any) -> list[str]:
    return [
        model_name.strip()
        for model_name in settings.external_openai_compatible_models.split(",")
        if model_name.strip()
    ]
