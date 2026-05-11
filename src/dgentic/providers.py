from typing import Any
from urllib.error import URLError

from dgentic.credentials import credential_reference_is_configured
from dgentic.events import event_log
from dgentic.provider_policy import (
    ProviderEgressPolicyError,
    normalize_provider_base_url,
    validate_provider_base_url,
)
from dgentic.provider_pricing import (
    provider_request_estimate_usd,
    validate_provider_pricing_catalog,
)
from dgentic.provider_routing import (
    ProviderRoleRoute,
    ProviderRoutingConfigurationError,
    provider_role_route_for,
    provider_role_routing,
    validate_provider_role_routing,
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
ROUTABLE_PROVIDER_IDS = {"ollama", "lm-studio", EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID}


class ProviderRoutingError(ValueError):
    """Raised when no provider can satisfy the requested routing policy."""


def default_providers() -> list[ProviderConfig]:
    settings = get_settings()
    external_enabled = _external_provider_configured(settings)
    external_models = _external_model_names(settings) if external_enabled else []
    return [
        ProviderConfig(
            id="ollama",
            name="Ollama",
            kind=ProviderKind.local,
            base_url=_safe_provider_base_url_for_display(settings.ollama_base_url),
            model_names=[],
            capabilities=["chat", "streaming", "local", "private"],
            estimated_latency_ms=250,
            estimated_cost_usd=0.0,
            permission_mode=PermissionMode.autopilot_safe,
            supports_streaming=True,
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
            model_names=external_models,
            capabilities=["chat", "streaming", "external", "openai-compatible", "high-capability"],
            estimated_latency_ms=800,
            estimated_cost_usd=_external_estimated_cost_usd(settings, external_models),
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
    validate_provider_pricing_catalog(get_settings())
    providers = []
    for provider in default_providers():
        health = check_provider_health(provider.id)
        providers.append(provider.model_copy(update={"model_names": health.model_names}))
    return providers


def check_provider_health(provider_id: str) -> ProviderHealth:
    validate_provider_pricing_catalog(get_settings())
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
    settings = get_settings()
    validate_provider_pricing_catalog(settings)
    validate_provider_role_routing(settings)
    _validate_provider_role_route_targets(settings)
    role_route = provider_role_route_for(settings, policy.role)
    providers = list_providers()
    scored = {provider.id: _score_provider(provider, policy) for provider in providers}
    if role_route is not None:
        return _choose_role_routed_provider(policy, role_route, providers, scored)

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


def _choose_role_routed_provider(
    policy: RoutingRequest,
    role_route: ProviderRoleRoute,
    providers: list[ProviderConfig],
    scored: dict[str, float],
) -> RoutingDecision:
    preferred = next(
        (provider for provider in providers if provider.id == role_route.provider_id), None
    )
    if preferred is None or scored.get(role_route.provider_id, 0.0) <= 0:
        raise ProviderRoutingError("No provider satisfies the configured role routing policy.")
    if role_route.model not in preferred.model_names:
        raise ProviderRoutingError("Configured role routing model is not available.")
    if (
        policy.max_cost_usd is not None
        and (model_estimate := _provider_model_estimate_usd(role_route)) is not None
        and model_estimate > policy.max_cost_usd
    ):
        raise ProviderRoutingError("No provider satisfies the configured role routing policy.")

    decision = RoutingDecision(
        provider_id=preferred.id,
        model_name=role_route.model,
        reason="Routing selected the configured provider for the requested role.",
        score=scored[preferred.id],
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
    if (
        policy.max_cost_usd is not None
        and provider.estimated_cost_usd is not None
        and provider.estimated_cost_usd > policy.max_cost_usd
    ):
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
        score += 0.1
    if provider.permission_mode == PermissionMode.autopilot_safe:
        score += 0.1

    return round(max(score, 0.0), 3)


def _validate_provider_role_route_targets(settings: Any) -> None:
    for route in provider_role_routing(settings).values():
        if route.provider_id not in ROUTABLE_PROVIDER_IDS:
            raise ProviderRoutingConfigurationError(
                "Provider role routing references an unsupported provider."
            )


def _provider_model_estimate_usd(route: ProviderRoleRoute) -> float | None:
    configured_estimate = provider_request_estimate_usd(
        get_settings(),
        provider_id=route.provider_id,
        model=route.model,
    )
    if configured_estimate is not None:
        return configured_estimate
    if route.provider_id in {"ollama", "lm-studio"}:
        return 0.0
    if route.provider_id == EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID:
        return 0.01
    return None


def _external_estimated_cost_usd(settings: Any, model_names: list[str]) -> float:
    if model_names:
        configured_estimate = provider_request_estimate_usd(
            settings,
            provider_id=EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID,
            model=model_names[0],
        )
        if configured_estimate is not None:
            return configured_estimate
    return 0.01


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
    credential_configured = _external_credential_configured(settings)
    return (
        bool(_safe_external_provider_base_url_for_display(settings))
        and credential_configured
        and bool(_external_model_names(settings))
    )


def _external_credential_configured(settings: Any) -> bool:
    credential_ref = settings.external_openai_compatible_credential_ref.strip()
    if credential_ref:
        return credential_reference_is_configured(
            credential_ref,
            purpose="provider",
            settings=settings,
        )
    return bool(settings.external_openai_compatible_api_key_env.strip())


def _external_model_names(settings: Any) -> list[str]:
    return [
        model_name.strip()
        for model_name in settings.external_openai_compatible_models.split(",")
        if model_name.strip()
    ]
