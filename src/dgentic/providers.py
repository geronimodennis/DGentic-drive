import json
from urllib.error import URLError
from urllib.request import Request, urlopen

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
from dgentic.settings import get_settings

MODEL_PROBE_TIMEOUT_SECONDS = 1.5


def default_providers() -> list[ProviderConfig]:
    settings = get_settings()
    return [
        ProviderConfig(
            id="ollama",
            name="Ollama",
            kind=ProviderKind.local,
            base_url=settings.ollama_base_url,
            model_names=[],
            capabilities=["chat", "local", "private"],
            estimated_latency_ms=250,
            estimated_cost_usd=0.0,
            permission_mode=PermissionMode.autopilot_safe,
        ),
        ProviderConfig(
            id="lm-studio",
            name="LM Studio",
            kind=ProviderKind.local,
            base_url=settings.lm_studio_base_url,
            model_names=[],
            capabilities=["chat", "local", "openai-compatible", "private"],
            estimated_latency_ms=300,
            estimated_cost_usd=0.0,
            permission_mode=PermissionMode.autopilot_safe,
        ),
        ProviderConfig(
            id="external-placeholder",
            name="External Provider Placeholder",
            kind=ProviderKind.external,
            model_names=["external-default"],
            capabilities=["chat", "external", "high-capability"],
            estimated_latency_ms=800,
            estimated_cost_usd=0.01,
            permission_mode=PermissionMode.approval_required,
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
    else:
        health = ProviderHealth(
            provider_id=provider.id,
            available=provider.enabled,
            message="Provider contract is configured; live adapter is not implemented yet.",
            model_names=provider.model_names,
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
    score = 0.0
    capabilities = set(provider.capabilities)
    required = set(policy.required_capabilities)

    if provider.enabled:
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
        payload = _get_json(f"{provider.base_url}/api/tags")
        model_names = [model["name"] for model in payload.get("models", []) if "name" in model]
        return ProviderHealth(
            provider_id=provider.id,
            available=True,
            message="Ollama is reachable.",
            model_names=model_names,
        )
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return ProviderHealth(
            provider_id=provider.id,
            available=False,
            message=f"Ollama is not reachable: {exc}",
        )


def _probe_lm_studio(provider: ProviderConfig) -> ProviderHealth:
    try:
        payload = _get_json(f"{provider.base_url}/v1/models")
        model_names = [model["id"] for model in payload.get("data", []) if "id" in model]
        return ProviderHealth(
            provider_id=provider.id,
            available=True,
            message="LM Studio is reachable.",
            model_names=model_names,
        )
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return ProviderHealth(
            provider_id=provider.id,
            available=False,
            message=f"LM Studio is not reachable: {exc}",
        )


def _get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=MODEL_PROBE_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))
